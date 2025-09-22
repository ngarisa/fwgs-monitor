export interface UserInfo {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
}

export interface ShippingInfo {
  address: string;
  city: string;
  zipCode: string;
}

export interface PaymentInfo {
  cardholderName: string;
  cardNumber: string;
  cvv: string;
  expiryDate: string;
}

export interface MonitorConfig {
  categoryIds: string[];
  scrapeIntervalMinutes: number;
  discordWebhookUrl: string;
  enableWatchlist: boolean;
  watchlistIds: string[];
  enableAutoCheckout: boolean;
  autoCheckoutKeywords: string[];
  autoCheckoutEvents: string[];
  dryRun: boolean;
}

export interface Product {
  id: string;
  name: string;
  price: number;
  imageUrl: string;
  pageUrl: string;
  quantity: number;
  isOnlineExclusive: boolean;
}

export interface MonitorStatus {
  isRunning: boolean;
  totalProducts: number;
  availableProducts: number;
  lastUpdate: string;
  errors: string[];
}

export interface KeywordRule {
  id: string;
  keywords: string[];
  matchMode: 'any' | 'all';
  searchFields: string[];
  enabled: boolean;
  name: string;
  description?: string;
}