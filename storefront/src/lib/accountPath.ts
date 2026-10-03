import { ROUTES } from "@/lib/router";

/** Same account URL the header and the account page already share. */
export function accountPath(tab = "commandes"): string {
  return `${ROUTES.account}?onglet=${tab}`;
}
