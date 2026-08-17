/** 工具菜单链接可以交给 React Router 和原生浏览器链接共同消费的导航属性。 */
export type ToolLinkProps = {
  target?: "_blank";
  rel?: "noopener noreferrer";
};

/**
 * 根据工具注册信息生成链接属性。新标签页入口同时切断 opener，
 * 保证原工作台继续保留时，新页面不能反向控制来源页面。
 */
export function readToolLinkProps(openInNewTab = false): ToolLinkProps {
  return openInNewTab ? { target: "_blank", rel: "noopener noreferrer" } : {};
}
