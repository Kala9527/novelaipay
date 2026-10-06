import { PageHeader } from '../components/UI'

export function ApiGuidePage() {
  const origin = window.location.origin
  return <div className="page guide-page"><PageHeader title="接口文档" subtitle="API 地址与生图接入" />
    <section className="guide-section"><h2>连接地址</h2><dl className="detail-grid"><dt>服务地址</dt><dd><code>{origin}</code></dd><dt>认证方式</dt><dd>在 API 密钥页面创建密钥，并在请求头中使用 <code>Authorization: Bearer pst-...</code></dd><dt>模型名称</dt><dd>从模型广场选择模型；密钥所属分组必须包含该模型。</dd></dl><p>从其他设备调用时，把地址中的主机名替换为该设备可访问的服务器地址；端口保持与部署配置一致。</p></section>
    <section className="guide-section"><h2>异步生图</h2><p>提交后返回任务 ID 和状态。使用同一密钥轮询任务，状态为 <code>succeeded</code> 后获取图片。</p><pre>{[`POST ${origin}/v1/images/generations`, 'Authorization: Bearer pst-你的密钥', 'Idempotency-Key: 每次生成使用唯一值', 'Content-Type: application/json', '', '{', '  "model": "模型广场中的模型名",', '  "prompt": "一幅城市夜景插画",', '  "size": "1024x1024",', '  "n": 1', '}'].join('\n')}</pre><pre>{[`GET ${origin}/v1/jobs/{任务ID}`, `GET ${origin}/v1/jobs/{任务ID}/image`].join('\n')}</pre></section>
    <section className="guide-section"><h2>酒馆生图配置</h2><dl className="detail-grid"><dt>生成方式</dt><dd>NovelAI → 第三方代理</dd><dt>代理 URL</dt><dd><code>{origin}/genarate</code></dd><dt>API 密钥</dt><dd>填写当前分组的 <code>pst-</code> 密钥</dd><dt>模型</dt><dd>填写模型广场中的公开模型名或有权限的专属模型名</dd></dl><p>酒馆的流式代理选项可以开启。代理接口会等待图片生成并返回可立即下载的短时效图片地址。</p></section>
    <section className="guide-section"><h2>模型列表与兼容接口</h2><pre>{[`GET ${origin}/v1/models`, 'Authorization: Bearer pst-你的密钥', '', `POST ${origin}/genarate`, 'Authorization: Bearer pst-你的密钥', 'Content-Type: application/json', '', '{"model":"模型名","prompt":"画面描述","size":"1024x1024"}'].join('\n')}</pre><p>所有时间按北京时间展示和筛选；费用以模型广场显示的分组定价为准。</p></section>
  </div>
}
