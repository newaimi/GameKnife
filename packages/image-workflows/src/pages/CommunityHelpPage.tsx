export function CommunityHelpPage() {
  return (
    <section className="settings-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">使用说明</p>
          <h1>游戏资源工作流</h1>
          <p>面向角色、道具、图标和素材板这类游戏图片资源，优先解决开发过程里重复出现的抠图、拆分和导出问题。</p>
        </div>
      </div>
      <div className="settings-grid">
        <section className="config-card wide">
          <h2>处理流程</h2>
          <p className="plain-text">上传游戏素材后选择“去背景”或“素材板拆分”。多人同时提交任务时，后端会串行执行 BiRefNet 推理，避免显存被并发任务打满。</p>
        </section>
      </div>
    </section>
  );
}
