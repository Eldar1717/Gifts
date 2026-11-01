/** API contract types (mirrors backend Pydantic schemas). */

export type Rarity = "common" | "uncommon" | "rare" | "epic" | "legendary";

export type ListingStatus = "active" | "reserved" | "sold" | "cancelled" | "expired";

export type OrderStatus =
  | "pending_payment"
  | "paid"
  | "fulfilled"
  | "failed"
  | "cancelled"
  | "expired"
  | "refund_pending"
  | "refunded";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface CollectionShort {
  id: number;
  slug: string;
  name: string;
  rarity: Rarity;
  cover_url: string;
  accent: string;
}

export interface Category {
  id: number;
  slug: string;
  name: string;
  emoji: string;
  description: string;
}

export interface CollectionPublic extends CollectionShort {
  description: string;
  status: string;
  is_featured: boolean;
  released_at: string | null;
  category: Category | null;
  ton_collection_address: string;
  chain_verified: boolean;
  items_count: number;
  items_sold: number;
  floor_price_stars: number | null;
}

export interface ItemCard {
  id: number;
  name: string;
  image_url: string;
  back_image_url: string;
  rarity: Rarity;
  glow: string;
  primary_price_stars: number;
  edition_size: number;
  minted_count: number;
  remaining: number;
  status: "draft" | "active" | "sold_out" | "archived";
  source: "internal" | "telegram_official" | "external_nft";
  is_tradeable: boolean;
  is_featured: boolean;
  collection: CollectionShort;
  created_at: string;
}

export interface UserShort {
  id: number;
  username: string;
  display_name: string;
  photo_url: string;
  rating: number | null;
}

export interface MarketCard {
  kind: "primary" | "resale";
  key: string;
  item: ItemCard;
  listing_id: number | null;
  ownership_id: number | null;
  price_stars: number;
  seller: UserShort | null;
  serial_number: number | null;
  listed_at: string | null;
  views: number;
}

export interface PricePoint {
  price_stars: number;
  event: string;
  created_at: string;
  listing_id: number | null;
}

export interface ItemDetail extends MarketCard {
  description: string;
  collection: CollectionPublic;
  price_history: PricePoint[];
  recent_sales: PricePoint[];
  owners_history: Array<{
    event: string;
    from: UserShort | null;
    to: UserShort;
    price_stars: number;
    created_at: string;
  }>;
  favorite: boolean;
  owned_by_me: boolean;
  can_buy: boolean;
  remaining: number;
  edition_size: number;
  minted_count: number;
}

export interface MarketplaceConfig {
  commission_percent: number;
  seller_share_percent: number;
  min_listing_price: number;
  max_listing_price: number;
  hold_hours: number;
  min_payout_stars: number;
  currency: string;
  seller_balance_type: string;
  payout_note: string;
  maintenance_mode: boolean;
  maintenance_message: string;
}

export interface HomeResponse {
  featured: ItemCard[];
  trending: MarketCard[];
  new_arrivals: ItemCard[];
  rare_collections: CollectionPublic[];
  recent_sales: Array<{
    item_name: string;
    image_url: string;
    rarity: Rarity;
    price_stars: number;
    sold_at: string;
    serial_number: number | null;
  }>;
  top_sellers: UserShort[];
  recommended: MarketCard[];
  stats: {
    total_volume_stars: number;
    sales_24h: number;
    active_listings: number;
    collectors: number;
  };
}

export interface UserPublic {
  id: number;
  telegram_id: number;
  username: string;
  first_name: string;
  last_name: string;
  photo_url: string;
  display_name: string;
  rating: number | null;
  sales_count: number;
  purchases_count: number;
  created_at: string;
}

export interface Balance {
  currency: string;
  pending_stars: number;
  available_stars: number;
  withdrawn_stars: number;
  lifetime_stars: number;
  hold_hours: number;
  can_request_payout: boolean;
  payout_note: string;
}

export interface Stats {
  gifts_owned: number;
  listings_active: number;
  sales_count: number;
  purchases_count: number;
  gross_sales_stars: number;
  gross_purchases_stars: number;
  lifetime_seller_stars: number;
  rating_count: number;
  rating: number | null;
}

export interface Me {
  user: UserPublic;
  is_admin: boolean;
  admin_role: string | null;
  settings: {
    show_collection: boolean;
    allow_offers: boolean;
    notify_sales: boolean;
    notify_market: boolean;
  };
  ton_address: string;
  stats: Stats;
  balance: Balance;
  unread_notifications: number;
}

export interface Listing {
  id: number;
  price_stars: number;
  status: ListingStatus;
  listed_at: string;
  reserved_until: string | null;
  views: number;
  seller: UserShort;
  ownership: {
    id: number;
    serial_number: number | null;
    owner: UserShort;
    acquired_at: string;
    acquired_price_stars: number;
  };
  item: ItemCard;
}

export interface OwnershipCard {
  id: number;
  serial_number: number | null;
  acquired_at: string;
  acquired_price_stars: number;
  acquisition_type: string;
  status: string;
  item: ItemCard;
  listing: {
    id: number;
    price_stars: number;
    status: string;
    listed_at: string;
    seller: UserShort;
  } | null;
  can_list: boolean;
  estimated_value_stars: number | null;
}

export interface OwnershipDetail extends OwnershipCard {
  history: Array<{
    event: string;
    from: UserShort | null;
    to: UserShort;
    price_stars: number;
    created_at: string;
  }>;
  price_history: PricePoint[];
}

export interface InvoiceResponse {
  order_id: number;
  order_number: string;
  amount_stars: number;
  currency: string;
  status: OrderStatus;
  invoice_url: string;
  expires_at: string | null;
  commission_stars: number;
  seller_amount_stars: number;
  item_name: string;
  dev_simulated: boolean;
}

export interface Order {
  id: number;
  order_number: string;
  status: OrderStatus;
  order_type: "primary" | "resale";
  amount_stars: number;
  commission_stars: number;
  seller_amount_stars: number;
  currency: string;
  created_at: string;
  paid_at: string | null;
  fulfilled_at: string | null;
  item: ItemCard;
  seller: UserShort | null;
  buyer: UserShort | null;
  serial_number: number | null;
  reviewed: boolean;
  can_review: boolean;
  failure_reason: string;
}

export interface OrderDetail extends Order {
  payment: {
    id: number;
    status: "pending" | "succeeded" | "failed" | "refunded";
    amount_stars: number;
    currency: string;
    telegram_payment_charge_id: string | null;
    provider_payment_charge_id: string | null;
    paid_at: string | null;
    created_at: string;
  } | null;
}

export interface Transaction {
  id: number;
  type: string;
  bucket: string;
  amount_stars: number;
  balance_after: number | null;
  description: string;
  order_id: number | null;
  created_at: string;
}

export interface NotificationItem {
  id: number;
  type: string;
  title: string;
  body: string;
  payload: string;
  is_read: boolean;
  created_at: string;
}

export interface Payout {
  id: number;
  user_id: number;
  amount_stars: number;
  method: string;
  destination: string;
  status: "requested" | "approved" | "rejected" | "paid";
  admin_note: string;
  created_at: string;
  decided_at: string | null;
  paid_at: string | null;
}

export interface Offer {
  id: number;
  ownership_id: number;
  price_stars: number;
  message: string;
  status: string;
  created_at: string;
  buyer: UserShort;
  item_name: string;
  image_url: string;
}

export interface Review {
  id: number;
  rating: number;
  comment: string;
  created_at: string;
  author: UserShort;
}

export interface SellerProfile {
  user: UserShort;
  stats: Stats;
  listings_count: number;
  collection_visible: boolean;
  recently_sold: string[];
}

export interface Meta {
  bot_username: string;
  webapp_url: string;
  dev_mode: boolean;
  bot_configured: boolean;
  ton_enabled: boolean;
  currency: string;
  app_name: string;
}

export interface AdminOverview {
  total_volume_stars: number;
  platform_revenue_stars: number;
  seller_credits_stars: number;
  orders_count: number;
  orders_paid_count: number;
  orders_fulfilled_count: number;
  active_users_7d: number;
  active_users_30d: number;
  users_total: number;
  active_listings: number;
  collections_total: number;
  gifts_minted: number;
  pending_payouts_stars: number;
  pending_payout_requests: number;
  open_reports: number;
  seller_pending_stars: number;
  seller_available_stars: number;
  revenue_24h_stars: number;
  volume_24h_stars: number;
  orders_24h: number;
  top_gifts: Array<{ id: number; name: string; sales: number; volume_stars: number }>;
  revenue_series: Array<{ date: string; revenue_stars: number; volume_stars: number; orders: number }>;
  recent_orders: Array<{
    id: number;
    order_number: string;
    item_name: string;
    amount_stars: number;
    status: string;
    buyer: UserShort | null;
    created_at: string;
  }>;
}

export interface AdminUserRow {
  id: number;
  telegram_id: number;
  username: string;
  display_name: string;
  photo_url: string;
  is_admin: boolean;
  is_blocked: boolean;
  admin_role: string | null;
  sales_count: number;
  purchases_count: number;
  gifts_owned: number;
  available_stars: number;
  pending_stars: number;
  created_at: string;
  last_seen_at: string;
}

export interface AdminSettings {
  commission_percent: number;
  min_listing_price: number;
  max_listing_price: number;
  hold_hours: number;
  maintenance_mode: boolean;
  maintenance_message: string;
  max_active_listings: number;
  min_payout_stars: number;
  payout_note: string;
  terms_url: string;
  updated_at: string;
  updated_by: UserShort | null;
}

export interface AdminItemRow {
  item: ItemCard;
  collection_name: string;
  minted_count: number;
  edition_size: number;
}

export interface AdminPayoutRow {
  id: number;
  user: UserShort;
  amount_stars: number;
  method: string;
  destination: string;
  status: string;
  admin_note: string;
  external_reference: string;
  created_at: string;
  decided_at: string | null;
  paid_at: string | null;
}

export interface AdminReportRow {
  id: number;
  reporter: UserShort;
  target_type: string;
  target_id: number;
  reason: string;
  details: string;
  status: string;
  resolution: string;
  created_at: string;
  resolved_at: string | null;
}

export interface AdminAuditRow {
  id: number;
  admin: UserShort | null;
  action: string;
  entity_type: string;
  entity_id: number | null;
  before: string;
  after: string;
  ip_address: string;
  created_at: string;
}

export interface AdminOrderRow {
  id: number;
  order_number: string;
  item_name: string;
  image_url: string;
  buyer: UserShort;
  seller: UserShort | null;
  amount_stars: number;
  commission_stars: number;
  seller_amount_stars: number;
  status: string;
  created_at: string;
  paid_at: string | null;
}
