import React, { useState, useEffect } from 'react';
import { MapPin, Save } from 'lucide-react';
import { ShippingInfo } from '../types';
import { storage } from '../utils/storage';

interface ShippingFormProps {
  onSave?: (info: ShippingInfo) => void;
}

export const ShippingForm: React.FC<ShippingFormProps> = ({ onSave }) => {
  const [shippingInfo, setShippingInfo] = useState<ShippingInfo>({
    address: '',
    city: '',
    zipCode: ''
  });
  const [isSaved, setIsSaved] = useState(false);

  useEffect(() => {
    const saved = storage.getShippingInfo();
    if (saved) {
      setShippingInfo(saved);
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    storage.setShippingInfo(shippingInfo);
    setIsSaved(true);
    onSave?.(shippingInfo);
    
    setTimeout(() => setIsSaved(false), 2000);
  };

  const handleChange = (field: keyof ShippingInfo, value: string) => {
    setShippingInfo(prev => ({ ...prev, [field]: value }));
    setIsSaved(false);
  };

  return (
    <div className="card">
      <div className="card-header">
        <MapPin className="w-6 h-6 text-primary-600" />
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Shipping Address</h2>
          <p className="text-sm text-gray-600">Where should we ship your orders?</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="input-group">
          <label className="input-label">Street Address</label>
          <input
            type="text"
            className="input-field"
            value={shippingInfo.address}
            onChange={(e) => handleChange('address', e.target.value)}
            placeholder="123 Main Street"
            required
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="input-group">
            <label className="input-label">City</label>
            <input
              type="text"
              className="input-field"
              value={shippingInfo.city}
              onChange={(e) => handleChange('city', e.target.value)}
              placeholder="Philadelphia"
              required
            />
          </div>
          
          <div className="input-group">
            <label className="input-label">ZIP Code</label>
            <input
              type="text"
              className="input-field"
              value={shippingInfo.zipCode}
              onChange={(e) => handleChange('zipCode', e.target.value)}
              placeholder="19106"
              required
            />
          </div>
        </div>

        <button
          type="submit"
          className={`btn w-full ${isSaved ? 'btn-success' : 'btn-primary'}`}
        >
          <Save className="w-4 h-4" />
          {isSaved ? 'Saved!' : 'Save Shipping Address'}
        </button>
      </form>
    </div>
  );
};