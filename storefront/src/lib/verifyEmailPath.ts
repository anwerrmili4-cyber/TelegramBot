import { ROUTES } from "@/lib/router";

export function verifyEmailPath(email: string, next?: string): string {
  const query = new URLSearchParams({ email });
  if (next) query.set("next", next);
  return `${ROUTES.verifyEmail}?${query}`;
}
