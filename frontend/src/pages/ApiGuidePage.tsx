import { useEffect, useState } from 'react'
import { PageHeader } from '../components/UI'
import { usePreferences } from '../lib/preferences'

const sectionIds = ['connection', 'asynchronous', 'editing', 'inpainting', 'references', 'tavern', 'compatibility'] as const
const tocTitles = { zh: '本页目录', en: 'On this page', ja: 'このページ' }

const content = {
  zh: {
    subtitle: 'API 地址与生图接入', connection: '连接地址', base: '服务地址', auth: '认证方式', authBody: '在 API 密钥页面创建密钥，在请求头中使用', model: '模型名称', modelBody: '从模型广场选择模型；密钥所属分组必须包含该模型。', hostHint: '从其他设备调用时，请使用该设备可访问的服务器地址；端口保持与部署配置一致。', asynchronous: '异步生图', asyncBody: '提交后返回任务 ID 和状态。使用同一密钥轮询任务，状态为 succeeded 后获取图片。', editing: '图生图与编辑生图', editingBody: '使用同一个提交接口，将原图和编辑要求放在请求体中。image 填 PNG/JPEG 的 Base64 内容或 data URL；strength 范围为 0 到 1，数值越大，改动越明显。每次新任务使用新的 Idempotency-Key。', inpainting: '局部重绘', inpaintingBody: '把需要修改的区域绘制在与原图同尺寸的 PNG 遮罩上。请求中同时提供 image 和 mask，服务会选择对应的 inpainting 模型。', imageLimits: '图片须为 PNG 或 JPEG 且不超过 12 MB；遮罩使用 PNG。以上模式只适用于支持相应功能的上游模型。', references: '参考图', referencesBody: '编辑时也可以附加风格参考图。references 最多 8 张；精准参考图使用 precise_reference，两者不能同时提供。', tavern: '酒馆生图配置', method: '生成方式', methodValue: 'NovelAI → 第三方代理', proxy: '代理 URL', tavernKey: 'API 密钥', tavernKeyBody: '填写当前分组的 pst- 密钥', tavernModel: '模型', tavernModelBody: '填写模型广场中的公开模型名或有权限的专属模型名', tavernBody: '酒馆的流式代理选项可以开启。代理接口会等待图片生成并返回可立即下载的短时效图片地址。', compatibility: '模型列表与兼容接口', billingNote: '所有时间按北京时间展示和筛选；费用以模型广场显示的分组定价为准。',
  },
  en: {
    subtitle: 'API base URL and image generation', connection: 'Connection', base: 'Base URL', auth: 'Authentication', authBody: 'Create a key on the API keys page and send it in the request header as', model: 'Model name', modelBody: 'Choose a model in the model plaza. Your key must belong to a group that contains it.', hostHint: 'When calling from another device, use a server address that device can reach. Keep the configured port.', asynchronous: 'Asynchronous generation', asyncBody: 'Submission returns a job ID and status. Poll with the same key; download the image when status is succeeded.', editing: 'Image to image and editing', editingBody: 'Use the same endpoint with the source image and editing prompt. image accepts PNG/JPEG Base64 or a data URL. strength ranges from 0 to 1; higher values make larger changes. Use a new Idempotency-Key for each job.', inpainting: 'Inpainting', inpaintingBody: 'Draw the area to edit in a PNG mask matching the source image size. Send both image and mask; the service selects a suitable inpainting model.', imageLimits: 'Images must be PNG or JPEG and at most 12 MB. Masks must be PNG. These modes require a compatible upstream model.', references: 'Reference images', referencesBody: 'You can add style references when editing. references accepts up to 8 images; precise_reference is for precise guidance. Do not use both together.', tavern: 'Tavern image generation', method: 'Generation mode', methodValue: 'NovelAI → Third-party proxy', proxy: 'Proxy URL', tavernKey: 'API key', tavernKeyBody: 'Use a pst- key from the current group', tavernModel: 'Model', tavernModelBody: 'Use a public model or a private model you can access', tavernBody: 'Streaming proxy can be enabled. The proxy waits for generation and returns a short-lived image URL for immediate download.', compatibility: 'Model list and compatible endpoints', billingNote: 'Dates are displayed and filtered in Beijing time. Charges follow the group prices in the model plaza.',
  },
  ja: {
    subtitle: 'API URL と画像生成の接続方法', connection: '接続先', base: 'サービス URL', auth: '認証方法', authBody: 'API キーページでキーを作成し、リクエストヘッダーに設定します：', model: 'モデル名', modelBody: 'モデル一覧から選びます。キーのグループにそのモデルが含まれている必要があります。', hostHint: '別の端末から呼び出す場合は、その端末から到達できるサーバーアドレスを使用し、設定されたポートを維持してください。', asynchronous: '非同期画像生成', asyncBody: '送信するとジョブ ID と状態が返ります。同じキーで状態を確認し、succeeded になったら画像を取得します。', editing: '画像からの生成と編集', editingBody: '同じエンドポイントに元画像と編集指示を送ります。image には PNG/JPEG の Base64 または data URL を指定します。strength は 0～1 で、大きいほど変更が強くなります。ジョブごとに新しい Idempotency-Key を使用してください。', inpainting: '部分修正', inpaintingBody: '元画像と同じサイズの PNG マスクに編集範囲を描きます。image と mask を送ると、対応するモデルが選択されます。', imageLimits: '画像は 12 MB 以下の PNG または JPEG、マスクは PNG です。対応する上流モデルが必要です。', references: '参照画像', referencesBody: '編集時にスタイル参照を追加できます。references は最大 8 枚です。精密参照には precise_reference を使用し、両方を同時に指定しないでください。', tavern: 'Tavern 画像生成設定', method: '生成方法', methodValue: 'NovelAI → サードパーティプロキシ', proxy: 'プロキシ URL', tavernKey: 'API キー', tavernKeyBody: '現在のグループの pst- キーを使用', tavernModel: 'モデル', tavernModelBody: '公開モデル、またはアクセス権のある専用モデルを使用', tavernBody: 'ストリーミングプロキシを有効にできます。生成完了後、すぐに取得できる短期間有効な画像 URL を返します。', compatibility: 'モデル一覧と互換 API', billingNote: '日時は北京時間で表示・検索されます。料金はモデル一覧に表示されるグループ料金に従います。',
  },
} as const

export function ApiGuidePage() {
  const { locale, t } = usePreferences()
  const text = content[locale]
  const [activeSection, setActiveSection] = useState<string>(sectionIds[0])
  useEffect(() => {
    const update = () => {
      let current: string = sectionIds[0]
      for (const id of sectionIds) {
        if ((document.getElementById(`guide-${id}`)?.getBoundingClientRect().top ?? Infinity) <= 190) current = id
      }
      if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2) current = sectionIds[sectionIds.length - 1]
      setActiveSection(current)
    }
    const target = document.getElementById(window.location.hash.slice(1))
    if (target?.classList.contains('guide-section')) target.scrollIntoView()
    update()
    window.addEventListener('scroll', update, { passive: true })
    return () => window.removeEventListener('scroll', update)
  }, [])
  const origin = window.location.origin
  const generation = [`POST ${origin}/v1/images/generations`, 'Authorization: Bearer pst-your-key', 'Idempotency-Key: unique-value-for-this-job', 'Content-Type: application/json', '', '{', '  "model": "model-name",', '  "prompt": "An illustrated city at night",', '  "size": "1024x1024",', '  "n": 1', '}'].join('\n')
  const edit = [`POST ${origin}/v1/images/generations`, 'Authorization: Bearer pst-your-key', 'Idempotency-Key: another-unique-value', 'Content-Type: application/json', '', '{', '  "model": "model-name",', '  "prompt": "Change the background to a rainy night",', '  "size": "1024x1024",', '  "parameters": {', '    "action": "img2img",', '    "image": "data:image/png;base64,<image-base64>",', '    "strength": 0.55,', '    "noise": 0', '  }', '}'].join('\n')
  const infill = [`POST ${origin}/v1/images/generations`, 'Authorization: Bearer pst-your-key', 'Idempotency-Key: another-unique-value', 'Content-Type: application/json', '', '{', '  "model": "model-name",', '  "prompt": "Change the view outside the window to snow",', '  "size": "1024x1024",', '  "parameters": {', '    "action": "infill",', '    "image": "data:image/png;base64,<image-base64>",', '    "mask": "data:image/png;base64,<mask-base64>",', '    "strength": 0.7,', '    "inpaint_img2img_strength": 0.8', '  }', '}'].join('\n')
  return <div className="page guide-page"><PageHeader title={t('guide')} subtitle={text.subtitle} />
    <div className="guide-layout"><div className="guide-body">
      <section className="guide-section" id="guide-connection"><h2>{text.connection}</h2><dl className="detail-grid"><dt>{text.base}</dt><dd><code>{origin}</code></dd><dt>{text.auth}</dt><dd>{text.authBody} <code>Authorization: Bearer pst-...</code></dd><dt>{text.model}</dt><dd>{text.modelBody}</dd></dl><p>{text.hostHint}</p></section>
      <section className="guide-section" id="guide-asynchronous"><h2>{text.asynchronous}</h2><p>{text.asyncBody}</p><pre>{generation}</pre><pre>{[`GET ${origin}/v1/jobs/{job-id}`, `GET ${origin}/v1/jobs/{job-id}/image`].join('\n')}</pre></section>
      <section className="guide-section" id="guide-editing"><h2>{text.editing}</h2><p>{text.editingBody}</p><pre>{edit}</pre></section>
      <section className="guide-section" id="guide-inpainting"><h2>{text.inpainting}</h2><p>{text.inpaintingBody}</p><pre>{infill}</pre><p>{text.imageLimits}</p></section>
      <section className="guide-section" id="guide-references"><h2>{text.references}</h2><p>{text.referencesBody}</p><pre>{['"parameters": {', '  "action": "generate",', '  "references": [{', '    "image": "data:image/png;base64,<reference-base64>",', '    "information_extracted": 1,', '    "strength": 0.6', '  }]', '}'].join('\n')}</pre></section>
      <section className="guide-section" id="guide-tavern"><h2>{text.tavern}</h2><dl className="detail-grid"><dt>{text.method}</dt><dd>{text.methodValue}</dd><dt>{text.proxy}</dt><dd><code>{origin}/genarate</code></dd><dt>{text.tavernKey}</dt><dd>{text.tavernKeyBody}</dd><dt>{text.tavernModel}</dt><dd>{text.tavernModelBody}</dd></dl><p>{text.tavernBody}</p></section>
      <section className="guide-section" id="guide-compatibility"><h2>{text.compatibility}</h2><pre>{[`GET ${origin}/v1/models`, 'Authorization: Bearer pst-your-key', '', `POST ${origin}/genarate`, 'Authorization: Bearer pst-your-key', 'Content-Type: application/json', '', '{"model":"model-name","prompt":"image description","size":"1024x1024"}'].join('\n')}</pre><p>{text.billingNote}</p></section>
    </div><nav className="guide-toc" aria-label={tocTitles[locale]}><span className="guide-toc-title">{tocTitles[locale]}</span><div className="guide-toc-links">{sectionIds.map((id, index) => <a key={id} href={`#guide-${id}`} className={activeSection === id ? 'active' : ''} aria-current={activeSection === id ? 'location' : undefined} onClick={() => setActiveSection(id)}><span>{String(index + 1).padStart(2, '0')}</span>{text[id]}</a>)}</div></nav></div>
  </div>
}
