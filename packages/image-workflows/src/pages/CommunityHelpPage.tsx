import { useTranslation } from "react-i18next";

export function CommunityHelpPage() {
  const { t } = useTranslation("help");

  return (
    <section className="settings-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">{t("eyebrow")}</p>
          <h1>{t("title")}</h1>
          <p>{t("description")}</p>
        </div>
      </div>
      <div className="settings-grid">
        <section className="config-card wide">
          <h2>{t("workflow.title")}</h2>
          <p className="plain-text">{t("workflow.description")}</p>
        </section>
      </div>
    </section>
  );
}
