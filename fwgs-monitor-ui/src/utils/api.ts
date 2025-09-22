import { MonitorStatus, Product } from '../types';

// Mock API functions - replace with actual API calls to your Python backend
export const api = {
  // Monitor control
  startMonitor: async (config: any): Promise<{ success: boolean; message: string }> => {
    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 1000));
    return { success: true, message: 'Monitor started successfully' };
  },

  stopMonitor: async (): Promise<{ success: boolean; message: string }> => {
    await new Promise(resolve => setTimeout(resolve, 500));
    return { success: true, message: 'Monitor stopped successfully' };
  },

  getMonitorStatus: async (): Promise<MonitorStatus> => {
    await new Promise(resolve => setTimeout(resolve, 300));
    return {
      isRunning: Math.random() > 0.5,
      totalProducts: Math.floor(Math.random() * 1000) + 500,
      availableProducts: Math.floor(Math.random() * 100) + 50,
      lastUpdate: new Date().toISOString(),
      errors: []
    };
  },

  // Products
  getProducts: async (): Promise<Product[]> => {
    await new Promise(resolve => setTimeout(resolve, 800));
    return [
      {
        id: '1',
        name: 'Blanton\'s Single Barrel Bourbon',
        price: 59.99,
        imageUrl: 'https://images.pexels.com/photos/602750/pexels-photo-602750.jpeg?auto=compress&cs=tinysrgb&w=300',
        pageUrl: 'https://example.com/product/1',
        quantity: 5,
        isOnlineExclusive: true
      },
      {
        id: '2',
        name: 'Weller Special Reserve',
        price: 29.99,
        imageUrl: 'https://images.pexels.com/photos/1283219/pexels-photo-1283219.jpeg?auto=compress&cs=tinysrgb&w=300',
        pageUrl: 'https://example.com/product/2',
        quantity: 0,
        isOnlineExclusive: false
      }
    ];
  },

  // Manual checkout
  triggerCheckout: async (productId: string): Promise<{ success: boolean; message: string }> => {
    await new Promise(resolve => setTimeout(resolve, 2000));
    return { 
      success: Math.random() > 0.3, 
      message: Math.random() > 0.3 ? 'Checkout initiated successfully' : 'Checkout failed - product out of stock'
    };
  }
};