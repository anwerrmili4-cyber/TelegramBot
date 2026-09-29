/** Shapes returned by the Python storefront API (`/api/storefront/*`). */

export type Offer = {
  id: number;
  package_number: string;
  name: string;
  description: string;
  price_millimes: number;
  currency: string;
  available: boolean;
  /** `-1` means unlimited stock. */
  stock: number;
  min_quantity: number;
  max_quantity: number;
  delivery_delay: string;
  period_days: number;
  warranty: string;
  featured: boolean;
  badge: string;
  image_url: string;
  category: string;
  category_label: string;
  service_id: number;
  service_name: string;
  service_emoji: string;
};

export type Category = { id: string; label: string };

export type PaymentMethod = { id: string; label: string };

export type Catalog = {
  ok: boolean;
  currency: string;
  whatsapp: string;
  max_cart_lines: number;
  services: { id: number; name: string; emoji: string; offers: Offer[] }[];
  categories: Category[];
  payment_methods: PaymentMethod[];
};

export type CheckoutItem = {
  offer_id: number;
  offer_name: string;
  service_name: string;
  quantity: number;
  unit_millimes: number;
  total_millimes: number;
};

export type CheckoutResult = {
  ok: boolean;
  reference: string;
  order_ids: number[];
  tracking_token: string;
  status: string;
  total_millimes: number;
  currency: string;
  automatic_confirmation: boolean;
  items: CheckoutItem[];
  whatsapp_url: string;
};

export type Customer = {
  id: number;
  name: string;
  email: string;
  created_at: number;
};

export type AuthSession = {
  ok: boolean;
  token: string;
  expires_at: number;
  customer: Customer;
};

/** Sign-up answer: no session until the emailed code is confirmed. */
export type VerificationRequired = {
  ok: boolean;
  verification_required: true;
  email: string;
};

/** A cart line: the live catalog offer plus the requested quantity. */
export type CartLine = { offer: Offer; quantity: number };
