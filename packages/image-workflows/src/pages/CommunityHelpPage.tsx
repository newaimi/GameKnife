import { Link } from "react-router-dom";
import { communityToolEntries } from "../tools/toolEntries";

export function CommunityHelpPage() {
  return (
    <section className="page-panel">
      <h1>帮助</h1>
      <div className="mini-list">
        {communityToolEntries.map((tool) => (
          <Link to={tool.route} key={tool.id}>
            {tool.label}
          </Link>
        ))}
      </div>
    </section>
  );
}
