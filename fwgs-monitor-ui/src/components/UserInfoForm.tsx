import React, { useState, useEffect } from 'react';
import { User, Save, AlertCircle } from 'lucide-react';
import { UserInfo } from '../types';
import { storage } from '../utils/storage';

interface UserInfoFormProps {
  onSave?: (info: UserInfo) => void;
}

export const UserInfoForm: React.FC<UserInfoFormProps> = ({ onSave }) => {
  const [userInfo, setUserInfo] = useState<UserInfo>({
    firstName: '',
    lastName: '',
    email: '',
    phone: ''
  });
  const [isSaved, setIsSaved] = useState(false);

  useEffect(() => {
    const saved = storage.getUserInfo();
    if (saved) {
      setUserInfo(saved);
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    storage.setUserInfo(userInfo);
    setIsSaved(true);
    onSave?.(userInfo);
    
    setTimeout(() => setIsSaved(false), 2000);
  };

  const handleChange = (field: keyof UserInfo, value: string) => {
    setUserInfo(prev => ({ ...prev, [field]: value }));
    setIsSaved(false);
  };

  return (
    <div className="card">
      <div className="card-header">
        <User className="w-6 h-6 text-primary-600" />
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Personal Information</h2>
          <p className="text-sm text-gray-600">Enter your details for checkout</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="input-group">
            <label className="input-label">First Name</label>
            <input
              type="text"
              className="input-field"
              value={userInfo.firstName}
              onChange={(e) => handleChange('firstName', e.target.value)}
              placeholder="John"
              required
            />
          </div>
          
          <div className="input-group">
            <label className="input-label">Last Name</label>
            <input
              type="text"
              className="input-field"
              value={userInfo.lastName}
              onChange={(e) => handleChange('lastName', e.target.value)}
              placeholder="Doe"
              required
            />
          </div>
        </div>

        <div className="input-group">
          <label className="input-label">Email Address</label>
          <input
            type="email"
            className="input-field"
            value={userInfo.email}
            onChange={(e) => handleChange('email', e.target.value)}
            placeholder="john.doe@example.com"
            required
          />
        </div>

        <div className="input-group">
          <label className="input-label">Phone Number</label>
          <input
            type="tel"
            className="input-field"
            value={userInfo.phone}
            onChange={(e) => handleChange('phone', e.target.value)}
            placeholder="(555) 123-4567"
            required
          />
        </div>

        <div className="flex items-center gap-2 p-3 bg-warning-50 border border-warning-200 rounded-lg">
          <AlertCircle className="w-5 h-5 text-warning-600 flex-shrink-0" />
          <p className="text-sm text-warning-800">
            This information will be used for automatic checkout. Keep it secure and accurate.
          </p>
        </div>

        <button
          type="submit"
          className={`btn w-full ${isSaved ? 'btn-success' : 'btn-primary'}`}
        >
          <Save className="w-4 h-4" />
          {isSaved ? 'Saved!' : 'Save Personal Information'}
        </button>
      </form>
    </div>
  );
};