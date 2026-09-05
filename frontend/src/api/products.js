import { api } from './client';

export const productsApi = {
  listProducts: (merchantId) => {
    const params = merchantId ? `?merchant_id=${merchantId}` : '';
    return api.get(`/products/${params}`);
  },
  getProduct: (id) => api.get(`/products/${id}/`),
  createProduct: (data) => api.post('/products/', data),
  updateProduct: (id, data) => api.patch(`/products/${id}/`, data),
  deleteProduct: (id) => api.delete(`/products/${id}/`),
};
