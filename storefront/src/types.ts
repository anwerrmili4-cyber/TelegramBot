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
  /** Empty when the service has no uploaded logo. */
  service_logo_url: string;
};

export type Category = { id: string; label: string };

/** A transfer method; `details` says where to send the money. */
export type PaymentMethod = { id: string; label: string; details: string };

export type Catalog = {
  ok: boolean;
  currency: string;
  max_cart_lines: number;
  services: { id: number; name: string; emoji: string; logo_url: string; offers: Offer[] }[];
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

export type CartStatus = "to_verify" | "confirmed" | "partial" | "delivered" | "cancelled" | "mixed";

export type CheckoutResult = {
  ok: boolean;
  reference: string;
  order_ids: number[];
  status: CartStatus;
  payment_method: string;
  total_millimes: number;
  currency: string;
  items: CheckoutItem[];
  balance_millimes: number;
};

export type Customer = {
  id: number;
  name: string;
  email: string;
  phone: string;
  email_confirmed: boolean;
  has_password: boolean;
  google: boolean;
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

export type AccountOrderItem = {
  id: number;
  offer_id: number | null;
  offer_name: string;
  service_name: string;
  quantity: number;
  unit_millimes: number;
  total_millimes: number;
  period_days: number;
  status: "to_verify" | "confirmed" | "delivered" | "cancelled";
  delivered_at: number | null;
  /** Access details, only once the line is delivered. */
  delivery: string;
  warranty_days?: number;
  warranty_open?: boolean;
  warranty_status?: string;
  warranty_id?: number | null;
  replacement?: string;
  /** Refusal note, when the claim was turned down. */
  warranty_note?: string;
};

export type AccountMessage = {
  id: number;
  sender: "client" | "admin";
  content: string;
  created_at: string | number | null;
};

export type AccountTicket = {
  id: number;
  category: string;
  status: string;
  order_id: number | null;
  created_at: string | number | null;
  updated_at: string | number | null;
  messages: AccountMessage[];
};

export type AccountTickets = { ok: boolean; tickets: AccountTicket[] };

export type AccountWarranty = {
  id: number;
  order_id: number;
  offer_name: string;
  status: string;
  reason: string;
  admin_note: string;
  refund_millimes: number;
  replacement: string;
  days_used: number;
  created_at: string | number | null;
  updated_at: string | number | null;
};

export type AccountWarranties = { ok: boolean; warranties: AccountWarranty[] };

export type AccountOrder = {
  reference: string;
  status: CartStatus;
  payment_method: string;
  payment_label: string;
  transaction_reference: string;
  total_millimes: number;
  refunded_millimes: number;
  created_at: number;
  paid_at: number | null;
  cancel_reason: string;
  /** Set once the order is paid and its invoice issued. */
  invoice_number?: string;
  items: AccountOrderItem[];
};

export type AccountOrders = {
  ok: boolean;
  email_confirmed: boolean;
  orders: AccountOrder[];
};

export type WalletTransaction = {
  id: number;
  kind: "deposit" | "purchase" | "refund" | "adjustment";
  label: string;
  amount_millimes: number;
  balance_after_millimes: number;
  reference: string;
  note: string;
  created_at: number;
};

export type Deposit = {
  id: number;
  method: string;
  method_label: string;
  amount_millimes: number;
  credited_millimes: number;
  transaction_reference: string;
  status: "pending" | "approved" | "rejected";
  reason: string;
  created_at: number;
  reviewed_at: number | null;
};

export type Wallet = {
  ok: boolean;
  balance_millimes: number;
  min_deposit_millimes: number;
  max_deposit_millimes: number;
  payment_methods: PaymentMethod[];
  transactions: WalletTransaction[];
  deposits: Deposit[];
};
