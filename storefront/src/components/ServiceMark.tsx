import { assetUrl } from "@/lib/api";
import type { Offer } from "@/types";

export function ServiceMark({ offer }: { offer: Offer }) {
  return (
    <span className={`offer-service${offer.service_logo_url ? " offer-service-logo" : ""}`} aria-hidden="true">
      {offer.service_logo_url ? (
        <img src={assetUrl(offer.service_logo_url)} alt="" loading="lazy" decoding="async" />
      ) : (
        offer.service_emoji
      )}
    </span>
  );
}
