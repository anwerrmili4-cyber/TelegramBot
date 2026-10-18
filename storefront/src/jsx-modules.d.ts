declare module "*.jsx" {
  import type { FC } from "react";

  const component: FC<Record<string, unknown>>;
  export default component;
}
