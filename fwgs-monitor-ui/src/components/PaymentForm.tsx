import React, { useState, useEffect } from 'react';
import { CreditCard, Save, Shield, AlertTriangle } from 'lucide-react';
import { PaymentInfo } from '../types';
import { storage } from '../utils/storage';

interface PaymentFormProps {
  onSave?: (info: PaymentInfo) => void;
}

export const PaymentForm: React.FC<PaymentFormProps> = ({ onSave }) => {
  const [paymentInfo, setPaymentInfo] = useState<PaymentInfo>({
    cardholderName: '',
    cardNumber: '',
    cvv: '',
    expiryDate: ''
  });
  const [isSaved, setIsSaved] = useState(false);
  const [showCardNumber, setShowCardNumber] = useState(false);

  useEffect(() => {
    const saved = storage.getPaymentInfo();
    if (saved) {
      setPaymentInfo(saved);
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    storage.setPaymentInfo(paymentInfo);
    setIsSaved(true);
    onSave?.(paymentInfo);
    
    setTimeout(() => setIsSaved(false), 2000);
  };

  const handleChange = (field: keyof PaymentInfo, value: string) => {
    setPaymentInfo(prev => ({ ...prev, [field]: value }));
    setIsSaved(false);
  };

  const formatCardNumber = (value: string) => {
    const v = value.replace(/\s+/g, '').replace(/[^0-9]/gi, '');
    const matches = v.match(/\d{4,16}/g);
    const match = matches && matches[0] || '';
    const parts = [];
    for (let i = 0, len = match.length; i < len; i += 4) {
      parts.push(match.substring(i, i + 4));
    }
    if (parts.length) {
      return parts.join(' ');
    } else {
      return v;
    }
  };

  const formatExpiryDate = (value: string) => {
    const v = value.replace(/\D/g, '');
    if (v.length >= 2) {
      return v.substring(0, 2) + '/' + v.substring(2, 4);
    }
    return v;
  };

  const maskCardNumber = (cardNumber: string) => {
    if (!cardNumber) return '';
    const cleaned = cardNumber.replace(/\s/g, '');
    if (cleaned.length <= 4) return cardNumber;
    return '**** **** **** ' + cleaned.slice(-4);
  };

  return (
    <div className="card">
      <div className="card-header">
        <CreditCard className="w-6 h-6 text-primary-600" />
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Payment Information</h2>
          <p className="text-sm text-gray-600">Secure payment details for checkout</p>
        </div>
      </div>

      <div className="mb-6 p-4 bg-error-50 border border-error-200 rounded-lg">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-error-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-medium text-error-900">Security Warning</h3>
            <p className="text-sm text-error-800 mt-1">
              This is a demo interface. Never enter real payment information in a production environment 
              without proper encryption and security measures.
            </p>
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="input-group">
          <label className="input-label">Cardholder Name</label>
          <input
            type="text"
            className="input-field"
            value={paymentInfo.cardholderName}
            onChange={(e) => handleChange('cardholderName', e.target.value)}
            placeholder="John Doe"
            required
          />
        </div>

        <div className="input-group">
          <div className="flex items-center justify-between">
            <label className="input-label">Card Number</label>
            <button
              type="button"
              onClick={() => setShowCardNumber(!showCardNumber)}
              className="text-sm text-primary-600 hover:text-primary-700 flex items-center gap-1"
            >
              <Shield className="w-4 h-4" />
              {showCardNumber ? 'Hide' : 'Show'}
            </button>
          </div>
          <input
            type="text"
            className="input-field font-mono"
            value={showCardNumber ? paymentInfo.cardNumber : maskCardNumber(paymentInfo.cardNumber)}
            onChange={(e) => handleChange('cardNumber', formatCardNumber(e.target.value))}
            placeholder="1234 5678 9012 3456"
            maxLength={19}
            required
            readOnly={!showCardNumber}
            onClick={() => !showCardNumber && setShowCardNumber(true)}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="input-group">
            <label className="input-label">Expiry Date</label>
            <input
              type="text"
              className="input-field font-mono"
              value={paymentInfo.expiryDate}
              onChange={(e) => handleChange('expiryDate', formatExpiryDate(e.target.value))}
              placeholder="MM/YY"
              maxLength={5}
              required
            />
          </div>
          
          <div className="input-group">
            <label className="input-label">CVV</label>
            <input
              type="password"
              className="input-field font-mono"
              value={paymentInfo.cvv}
              onChange={(e) => handleChange('cvv', e.target.value.replace(/\D/g, ''))}
              placeholder="123"
              maxLength={4}
              required
            />
          </div>
        </div>

        <button
          type="submit"
          className={`btn w-full ${isSaved ? 'btn-success' : 'btn-primary'}`}
        >
          <Save className="w-4 h-4" />
          {isSaved ? 'Saved!' : 'Save Payment Information'}
        </button>
      </form>
    </div>
  );
};