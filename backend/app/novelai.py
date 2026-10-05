"""NovelAI text-to-image parameters and Anlas estimate.

NovelAI documents the free-generation rules but does not publish a complete
current cost formula. The estimate below follows the community SDK's V3+
formula; an administrator sets the platform's CNY-per-Anlas rate.
"""

import math
import base64
import hashlib
import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from pydantic import BaseModel, Field, model_validator


SAMPLERS = {
    'k_euler_ancestral', 'k_euler', 'k_dpmpp_2m', 'k_dpmpp_2s_ancestral',
    'k_dpmpp_sde', 'k_dpm_2', 'k_dpm_fast', 'ddim',
}
INPUT_DIR = Path(__file__).resolve().parents[2] / 'data' / 'inputs'


class ReferenceImage(BaseModel):
    image: str
    information_extracted: float = Field(default=1, ge=0, le=1)
    strength: float = Field(default=0.6, ge=0, le=1)
    fidelity: float = Field(default=1, ge=0, le=1)
    description: str = Field(default='character&style', pattern=r'^(character|character&style|style)$')


class CharacterPrompt(BaseModel):
    prompt: str = Field(default='', max_length=4000)
    negative_prompt: str = Field(default='', max_length=4000)
    center: float = Field(default=0.5, ge=0, le=1)
    top: float = Field(default=0.5, ge=0, le=1)


class ImageParameters(BaseModel):
    steps: int = Field(default=23, ge=1, le=50)
    scale: float = Field(default=4.0, ge=0, le=30)
    sampler: str = 'k_euler_ancestral'
    negative_prompt: str = Field(default='', max_length=4000)
    seed: int | None = Field(default=None, ge=0, le=9999999999)
    quality_toggle: bool = False
    smea: bool = False
    smea_dyn: bool = False
    cfg_rescale: float = Field(default=0, ge=0, le=1)
    noise_schedule: str = 'karras'
    dynamic_thresholding: bool = False
    variety_boost: bool = False
    skip_cfg_above_sigma: float | None = Field(default=None, ge=0)
    action: str = 'generate'
    image: str | None = None
    mask: str | None = None
    strength: float = Field(default=0.7, ge=0, le=1)
    noise: float = Field(default=0, ge=0, le=1)
    inpaint_img2img_strength: float | None = Field(default=None, ge=0, le=1)
    references: list[ReferenceImage] = Field(default_factory=list, max_length=8)
    character_prompts: list[CharacterPrompt] = Field(default_factory=list, max_length=6)
    precise_reference: ReferenceImage | None = None

    @model_validator(mode='after')
    def validate_options(self):
        if self.sampler not in SAMPLERS:
            raise ValueError('Unsupported sampler')
        if self.noise_schedule not in {'karras', 'native', 'exponential', 'polyexponential'}:
            raise ValueError('Unsupported noise schedule')
        if self.smea_dyn and not self.smea:
            raise ValueError('SMEA DYN requires SMEA')
        if self.action not in {'generate', 'img2img', 'infill'}:
            raise ValueError('Unsupported image action')
        if self.action != 'generate' and not self.image:
            raise ValueError('Image input is required for image-to-image or inpaint')
        if self.action == 'infill' and not self.mask:
            raise ValueError('Mask is required for inpaint')
        if self.mask and self.action != 'infill':
            raise ValueError('Mask requires inpaint action')
        if self.references and self.precise_reference:
            raise ValueError('Vibe and character reference cannot be combined')
        return self


def _store_image(value: str, token_ok: bool = False) -> str:
    if value.startswith('asset:'):
        raise ValueError('Asset references cannot be submitted by clients')
    encoded = value.split(',', 1)[1] if value.startswith('data:image/') and ',' in value else value
    if len(encoded) > 16 * 1024 * 1024:
        raise ValueError('Input image exceeds 12 MB')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError('Invalid base64 image') from exc
    if not raw or len(raw) > 12 * 1024 * 1024 or (not token_ok and not raw.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff'))):
        raise ValueError('Input must be a PNG or JPEG under 12 MB')
    digest = hashlib.sha256(raw).hexdigest()
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = INPUT_DIR / digest
    if not path.exists():
        path.write_bytes(raw)
    return 'asset:' + digest


def store_image_inputs(params: ImageParameters) -> dict:
    data = params.model_dump()
    for key in ('image', 'mask'):
        if data[key]:
            data[key] = _store_image(data[key])
    for item in data['references']:
        item['image'] = _store_image(item['image'], token_ok=True)
    if data['precise_reference']:
        data['precise_reference']['image'] = _store_image(data['precise_reference']['image'])
    return data


def _load_image(value: str) -> str:
    if not value.startswith('asset:') or len(value) != 70:
        raise ValueError('Invalid stored image reference')
    return base64.b64encode((INPUT_DIR / value[6:]).read_bytes()).decode('ascii')


def _character_reference_image(value: str) -> str:
    source = base64.b64decode(_load_image(value))
    try:
        with Image.open(io.BytesIO(source)) as opened:
            if opened.width > 4096 or opened.height > 4096 or opened.width * opened.height > 16_000_000:
                raise ValueError('Character reference image is too large')
            image = opened.convert('RGB')
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError('Invalid character reference image') from exc
    ratio = image.width / image.height
    target = (1536, 1024) if ratio > 1.25 else (1024, 1536) if ratio < 0.8 else (1472, 1472)
    image.thumbnail(target, Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', target, (0, 0, 0))
    canvas.paste(image, ((target[0] - image.width) // 2, (target[1] - image.height) // 2))
    output = io.BytesIO()
    canvas.save(output, 'PNG')
    return base64.b64encode(output.getvalue()).decode('ascii')


def validate_size(size: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in size.lower().split('x'))
    except (TypeError, ValueError) as exc:
        raise ValueError('Size must be WIDTHxHEIGHT') from exc
    if width % 64 or height % 64 or min(width, height) < 64 or width * height > 1024 * 3072:
        raise ValueError('Size must be multiples of 64 and at most 3,145,728 pixels')
    return width, height


def estimate_anlas(model: str, size: str, params: ImageParameters, opus_free: bool = False) -> int:
    width, height = validate_size(size)
    pixels = max(width * height, 65536)
    base = math.ceil(0.000002951823174884865 * pixels +
                     0.0000005753298233447344 * pixels * params.steps)
    supports_smea = not model.startswith(('nai-diffusion-4', 'nai-diffusion-5'))
    factor = 1.4 if supports_smea and params.smea_dyn else 1.2 if supports_smea and params.smea else 1.0
    cost = max(2, math.ceil(base * factor))
    feature_cost = 2 * len(params.references) + (5 if params.precise_reference else 0)
    # V5's free allowance depends on upstream usage counters, which are not exposed here.
    if opus_free and not model.startswith('nai-diffusion-5') and params.steps <= 28 and pixels <= 1024 * 1024:
        return feature_cost
    return cost + feature_cost


def generation_payload(model: str, prompt: str, size: str, params: ImageParameters) -> dict:
    width, height = validate_size(size)
    skip_sigma = params.skip_cfg_above_sigma
    if skip_sigma is None and params.variety_boost:
        # SillyTavern's Variety+ threshold scales with image area.
        skip_sigma = math.sqrt(width * height / 1011712) * (58 if 'nai-diffusion-4-5' in model else 19)
    if params.action == 'infill' and not model.endswith('-inpainting'):
        model = {'nai-diffusion-4-curated-preview': 'nai-diffusion-4-curated-inpainting'}.get(
            model, model + '-inpainting')
    supports_smea = not model.startswith(('nai-diffusion-4', 'nai-diffusion-5'))
    settings = {
        'width': width, 'height': height, 'steps': params.steps, 'scale': params.scale,
        'sampler': params.sampler, 'negative_prompt': params.negative_prompt,
        'n_samples': 1, 'qualityToggle': params.quality_toggle,
        'sm': params.smea and supports_smea, 'sm_dyn': params.smea_dyn and supports_smea,
        'cfg_rescale': params.cfg_rescale, 'noise_schedule': params.noise_schedule,
        'params_version': 3, 'prefer_brownian': True, 'ucPreset': 0,
        'dynamic_thresholding': params.dynamic_thresholding,
        'skip_cfg_above_sigma': skip_sigma,
        'add_original_image': False, 'characterPrompts': [],
        'reference_image_multiple': [], 'reference_information_extracted_multiple': [],
        'reference_strength_multiple': [],
    }
    if params.seed is not None:
        settings['seed'] = params.seed
    if model.startswith(('nai-diffusion-4', 'nai-diffusion-5')):
        characters = [{'char_caption': item.prompt, 'centers': [{'x': item.center, 'y': item.top}]}
                      for item in params.character_prompts]
        negatives = [{'char_caption': item.negative_prompt, 'centers': [{'x': item.center, 'y': item.top}]}
                     for item in params.character_prompts]
        use_coords = any(item.center != 0.5 or item.top != 0.5 for item in params.character_prompts)
        settings['v4_prompt'] = {'caption': {'base_caption': prompt, 'char_captions': characters},
                                 'use_coords': use_coords, 'use_order': True}
        settings['v4_negative_prompt'] = {'caption': {
            'base_caption': params.negative_prompt, 'char_captions': negatives}}
    if params.action != 'generate':
        settings.update(image=_load_image(params.image), strength=params.strength, noise=params.noise)
        settings['sm'] = False
        settings['sm_dyn'] = False
    if params.action == 'infill':
        settings['mask'] = _load_image(params.mask)
        inpaint_strength = params.inpaint_img2img_strength
        if inpaint_strength is not None:
            settings['inpaintImg2ImgStrength'] = inpaint_strength
            if inpaint_strength < 1:
                settings['img2img'] = {'strength': inpaint_strength, 'color_correct': True}
    if params.references:
        settings['reference_image_multiple'] = [_load_image(item.image) for item in params.references]
        settings['reference_information_extracted_multiple'] = [item.information_extracted for item in params.references]
        settings['reference_strength_multiple'] = [item.strength for item in params.references]
        settings['normalize_reference_strength_multiple'] = True
    if params.precise_reference:
        ref = params.precise_reference
        settings['director_reference_images'] = [_character_reference_image(ref.image)]
        settings['director_reference_information_extracted'] = [ref.information_extracted]
        settings['director_reference_strength_values'] = [ref.strength]
        settings['director_reference_secondary_strength_values'] = [ref.fidelity]
        settings['director_reference_descriptions'] = [{'caption': {
            'base_caption': ref.description, 'char_captions': []}, 'legacy_uc': False}]
    return {'input': prompt, 'model': model, 'action': params.action, 'parameters': settings}
