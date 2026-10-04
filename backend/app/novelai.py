"""NovelAI text-to-image parameters and Anlas estimate.

NovelAI documents the free-generation rules but does not publish a complete
current cost formula. The estimate below follows the community SDK's V3+
formula; an administrator sets the platform's CNY-per-Anlas rate.
"""

import math

from pydantic import BaseModel, Field, model_validator


SAMPLERS = {
    'k_euler_ancestral', 'k_euler', 'k_dpmpp_2m', 'k_dpmpp_2s_ancestral',
    'k_dpmpp_sde', 'k_dpm_2', 'k_dpm_fast', 'ddim',
}


class ImageParameters(BaseModel):
    steps: int = Field(default=23, ge=1, le=50)
    scale: float = Field(default=4.0, ge=0, le=30)
    sampler: str = 'k_euler_ancestral'
    negative_prompt: str = Field(default='', max_length=4000)
    seed: int | None = Field(default=None, ge=0, le=4294967295)
    quality_toggle: bool = True
    smea: bool = False
    smea_dyn: bool = False
    cfg_rescale: float = Field(default=0, ge=0, le=1)
    noise_schedule: str = 'karras'

    @model_validator(mode='after')
    def validate_options(self):
        if self.sampler not in SAMPLERS:
            raise ValueError('Unsupported sampler')
        if self.noise_schedule not in {'karras', 'native', 'exponential', 'polyexponential'}:
            raise ValueError('Unsupported noise schedule')
        if self.smea_dyn and not self.smea:
            raise ValueError('SMEA DYN requires SMEA')
        return self


def validate_size(size: str) -> tuple[int, int]:
    width, height = (int(part) for part in size.split('x'))
    if width % 64 or height % 64 or min(width, height) < 64 or width * height > 1024 * 3072:
        raise ValueError('Size must be multiples of 64 and at most 3,145,728 pixels')
    return width, height


def estimate_anlas(model: str, size: str, params: ImageParameters, opus_free: bool = False) -> int:
    width, height = validate_size(size)
    pixels = max(width * height, 65536)
    base = math.ceil(0.000002951823174884865 * pixels +
                     0.0000005753298233447344 * pixels * params.steps)
    factor = 1.4 if params.smea_dyn else 1.2 if params.smea else 1.0
    cost = max(2, math.ceil(base * factor))
    # V5's free allowance depends on upstream usage counters, which are not exposed here.
    if opus_free and not model.startswith('nai-diffusion-5') and params.steps <= 28 and pixels <= 1024 * 1024:
        return 0
    return cost


def generation_payload(model: str, prompt: str, size: str, params: ImageParameters) -> dict:
    width, height = validate_size(size)
    settings = {
        'width': width, 'height': height, 'steps': params.steps, 'scale': params.scale,
        'sampler': params.sampler, 'negative_prompt': params.negative_prompt,
        'n_samples': 1, 'qualityToggle': params.quality_toggle,
        'sm': params.smea, 'sm_dyn': params.smea_dyn,
        'cfg_rescale': params.cfg_rescale, 'noise_schedule': params.noise_schedule,
    }
    if params.seed is not None:
        settings['seed'] = params.seed
    if model.startswith(('nai-diffusion-4', 'nai-diffusion-5')):
        settings['v4_prompt'] = {'caption': {'base_caption': prompt, 'char_captions': []},
                                 'use_coords': False, 'use_order': True}
        settings['v4_negative_prompt'] = {'caption': {
            'base_caption': params.negative_prompt, 'char_captions': []}}
    return {'input': prompt, 'model': model, 'action': 'generate', 'parameters': settings}
