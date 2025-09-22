import React, { useState, useEffect } from 'react';
import { Package, ExternalLink, ShoppingCart, RefreshCw, Filter } from 'lucide-react';
import { Product } from '../types';
import { api } from '../utils/api';

export const ProductList: React.FC = () => {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'available' | 'out-of-stock'>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);

  useEffect(() => {
    loadProducts();
  }, []);

  const loadProducts = async () => {
    setLoading(true);
    try {
      const productData = await api.getProducts();
      setProducts(productData);
    } catch (error) {
      console.error('Failed to load products:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCheckout = async (productId: string) => {
    setCheckoutLoading(productId);
    try {
      const result = await api.triggerCheckout(productId);
      if (result.success) {
        alert('Checkout initiated successfully!');
      } else {
        alert(`Checkout failed: ${result.message}`);
      }
    } catch (error) {
      alert('Checkout failed: Network error');
    } finally {
      setCheckoutLoading(null);
    }
  };

  const filteredProducts = products.filter(product => {
    const matchesSearch = product.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesFilter = 
      filter === 'all' || 
      (filter === 'available' && product.quantity > 0) ||
      (filter === 'out-of-stock' && product.quantity === 0);
    
    return matchesSearch && matchesFilter;
  });

  const availableCount = products.filter(p => p.quantity > 0).length;
  const outOfStockCount = products.filter(p => p.quantity === 0).length;

  return (
    <div className="card">
      <div className="card-header">
        <Package className="w-6 h-6 text-primary-600" />
        <div className="flex-1">
          <h2 className="text-xl font-semibold text-gray-900">Product Catalog</h2>
          <p className="text-sm text-gray-600">Monitor and manage product availability</p>
        </div>
        <button
          onClick={loadProducts}
          className="btn btn-secondary"
          disabled={loading}
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-gray-50 p-4 rounded-lg">
          <div className="text-2xl font-bold text-gray-900">{products.length}</div>
          <div className="text-sm text-gray-600">Total Products</div>
        </div>
        <div className="bg-success-50 p-4 rounded-lg">
          <div className="text-2xl font-bold text-success-700">{availableCount}</div>
          <div className="text-sm text-success-600">Available</div>
        </div>
        <div className="bg-error-50 p-4 rounded-lg">
          <div className="text-2xl font-bold text-error-700">{outOfStockCount}</div>
          <div className="text-sm text-error-600">Out of Stock</div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="flex-1">
          <input
            type="text"
            className="input-field"
            placeholder="Search products..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-gray-500" />
          <select
            className="input-field"
            value={filter}
            onChange={(e) => setFilter(e.target.value as any)}
          >
            <option value="all">All Products</option>
            <option value="available">Available Only</option>
            <option value="out-of-stock">Out of Stock</option>
          </select>
        </div>
      </div>

      {/* Product Grid */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-8 h-8 animate-spin text-primary-600" />
          <span className="ml-2 text-gray-600">Loading products...</span>
        </div>
      ) : filteredProducts.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <Package className="w-12 h-12 mx-auto mb-4 text-gray-300" />
          <p>No products found matching your criteria.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredProducts.map((product) => (
            <ProductCard
              key={product.id}
              product={product}
              onCheckout={handleCheckout}
              isCheckoutLoading={checkoutLoading === product.id}
            />
          ))}
        </div>
      )}
    </div>
  );
};

interface ProductCardProps {
  product: Product;
  onCheckout: (productId: string) => void;
  isCheckoutLoading: boolean;
}

const ProductCard: React.FC<ProductCardProps> = ({ product, onCheckout, isCheckoutLoading }) => {
  const isAvailable = product.quantity > 0;

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden hover:shadow-md transition-shadow">
      <div className="aspect-w-16 aspect-h-9 bg-gray-100">
        <img
          src={product.imageUrl}
          alt={product.name}
          className="w-full h-48 object-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).src = 'https://images.pexels.com/photos/602750/pexels-photo-602750.jpeg?auto=compress&cs=tinysrgb&w=300';
          }}
        />
      </div>
      
      <div className="p-4">
        <div className="flex items-start justify-between mb-2">
          <h3 className="font-medium text-gray-900 text-sm leading-tight">{product.name}</h3>
          {product.isOnlineExclusive && (
            <span className="inline-flex items-center px-2 py-1 bg-primary-100 text-primary-800 text-xs rounded-full ml-2 flex-shrink-0">
              Online
            </span>
          )}
        </div>
        
        <div className="flex items-center justify-between mb-3">
          <span className="text-lg font-bold text-gray-900">
            ${product.price.toFixed(2)}
          </span>
          <span className={`status-indicator ${isAvailable ? 'status-running' : 'status-stopped'}`}>
            {isAvailable ? `${product.quantity} in stock` : 'Out of stock'}
          </span>
        </div>
        
        <div className="flex gap-2">
          <a
            href={product.pageUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-secondary flex-1 text-sm"
          >
            <ExternalLink className="w-3 h-3" />
            View
          </a>
          
          {isAvailable && (
            <button
              onClick={() => onCheckout(product.id)}
              disabled={isCheckoutLoading}
              className="btn btn-primary flex-1 text-sm"
            >
              {isCheckoutLoading ? (
                <RefreshCw className="w-3 h-3 animate-spin" />
              ) : (
                <ShoppingCart className="w-3 h-3" />
              )}
              {isCheckoutLoading ? 'Processing...' : 'Checkout'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};