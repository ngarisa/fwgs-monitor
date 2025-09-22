import React, { useState } from 'react';
import { Monitor, User, MapPin, CreditCard, Settings, Package, Tag } from 'lucide-react';
import { UserInfoForm } from './components/UserInfoForm';
import { ShippingForm } from './components/ShippingForm';
import { PaymentForm } from './components/PaymentForm';
import { MonitorConfig } from './components/MonitorConfig';
import { ProductList } from './components/ProductList';
import { KeywordManager } from './components/KeywordManager';

type TabType = 'personal' | 'shipping' | 'payment' | 'monitor' | 'products' | 'keywords';

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('personal');

  const tabs = [
    { id: 'personal' as TabType, label: 'Personal Info', icon: User },
    { id: 'shipping' as TabType, label: 'Shipping', icon: MapPin },
    { id: 'payment' as TabType, label: 'Payment', icon: CreditCard },
    { id: 'monitor' as TabType, label: 'Monitor', icon: Settings },
    { id: 'keywords' as TabType, label: 'Keywords', icon: Tag },
    { id: 'products' as TabType, label: 'Products', icon: Package },
  ];

  const renderContent = () => {
    switch (activeTab) {
      case 'personal':
        return <UserInfoForm />;
      case 'shipping':
        return <ShippingForm />;
      case 'payment':
        return <PaymentForm />;
      case 'monitor':
        return <MonitorConfig />;
      case 'keywords':
        return <KeywordManager />;
      case 'products':
        return <ProductList />;
      default:
        return <UserInfoForm />;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <Monitor className="w-8 h-8 text-primary-600" />
              <div>
                <h1 className="text-xl font-bold text-gray-900">FWGS Monitor</h1>
                <p className="text-sm text-gray-600">Fine Wine & Good Spirits Product Monitor</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-success-500 rounded-full animate-pulse"></div>
              <span className="text-sm text-gray-600">System Ready</span>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col lg:flex-row gap-8">
          {/* Sidebar Navigation */}
          <div className="lg:w-64 flex-shrink-0">
            <nav className="space-y-2">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-colors ${
                      activeTab === tab.id
                        ? 'bg-primary-100 text-primary-700 border border-primary-200'
                        : 'text-gray-700 hover:bg-gray-100'
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                    <span className="font-medium">{tab.label}</span>
                  </button>
                );
              })}
            </nav>

            {/* Quick Stats */}
            <div className="mt-8 p-4 bg-white rounded-lg border border-gray-200">
              <h3 className="font-medium text-gray-900 mb-3">Quick Stats</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">Status:</span>
                  <span className="text-success-600 font-medium">Ready</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Products:</span>
                  <span className="text-gray-900 font-medium">1,247</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Available:</span>
                  <span className="text-success-600 font-medium">89</span>
                </div>
              </div>
            </div>
          </div>

          {/* Main Content */}
          <div className="flex-1">
            <div className="animate-fade-in">
              {renderContent()}
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 mt-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-600">
              FWGS Monitor - Automated product monitoring and checkout system
            </p>
            <div className="flex items-center gap-4 text-sm text-gray-500">
              <span>Built with React & TypeScript</span>
              <span>•</span>
              <span>Powered by Python Backend</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;