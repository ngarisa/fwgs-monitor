import { UserInfo, ShippingInfo, PaymentInfo, MonitorConfig, KeywordRule } from '../types';

const STORAGE_KEYS = {
  USER_INFO: 'fwgs_user_info',
  SHIPPING_INFO: 'fwgs_shipping_info',
  PAYMENT_INFO: 'fwgs_payment_info',
  MONITOR_CONFIG: 'fwgs_monitor_config',
  KEYWORD_RULES: 'fwgs_keyword_rules',
} as const;

export const storage = {
  // User Info
  getUserInfo: (): UserInfo | null => {
    const data = localStorage.getItem(STORAGE_KEYS.USER_INFO);
    return data ? JSON.parse(data) : null;
  },
  
  setUserInfo: (info: UserInfo): void => {
    localStorage.setItem(STORAGE_KEYS.USER_INFO, JSON.stringify(info));
  },

  // Shipping Info
  getShippingInfo: (): ShippingInfo | null => {
    const data = localStorage.getItem(STORAGE_KEYS.SHIPPING_INFO);
    return data ? JSON.parse(data) : null;
  },
  
  setShippingInfo: (info: ShippingInfo): void => {
    localStorage.setItem(STORAGE_KEYS.SHIPPING_INFO, JSON.stringify(info));
  },

  // Payment Info (Note: In production, never store real payment info in localStorage)
  getPaymentInfo: (): PaymentInfo | null => {
    const data = localStorage.getItem(STORAGE_KEYS.PAYMENT_INFO);
    return data ? JSON.parse(data) : null;
  },
  
  setPaymentInfo: (info: PaymentInfo): void => {
    localStorage.setItem(STORAGE_KEYS.PAYMENT_INFO, JSON.stringify(info));
  },

  // Monitor Config
  getMonitorConfig: (): MonitorConfig | null => {
    const data = localStorage.getItem(STORAGE_KEYS.MONITOR_CONFIG);
    return data ? JSON.parse(data) : null;
  },
  
  setMonitorConfig: (config: MonitorConfig): void => {
    localStorage.setItem(STORAGE_KEYS.MONITOR_CONFIG, JSON.stringify(config));
  },

  // Keyword Rules
  getKeywordRules: (): KeywordRule[] => {
    const data = localStorage.getItem(STORAGE_KEYS.KEYWORD_RULES);
    return data ? JSON.parse(data) : [];
  },
  
  setKeywordRules: (rules: KeywordRule[]): void => {
    localStorage.setItem(STORAGE_KEYS.KEYWORD_RULES, JSON.stringify(rules));
  },

  // Clear all data
  clearAll: (): void => {
    Object.values(STORAGE_KEYS).forEach(key => {
      localStorage.removeItem(key);
    });
  }
};