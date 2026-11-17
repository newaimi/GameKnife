/** Navigation attributes shared by React Router links and native browser links. */
export type ToolLinkProps = {
  target?: "_blank";
  rel?: "noopener noreferrer";
};

/**
 * Builds link attributes from the tool registry. New-tab entries sever opener access so the destination cannot
 * control the workbench that launched it.
 */
export function readToolLinkProps(openInNewTab = false): ToolLinkProps {
  return openInNewTab ? { target: "_blank", rel: "noopener noreferrer" } : {};
}
