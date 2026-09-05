import { api } from './client';

export const merchantsApi = {
  list: () => api.get('/merchants/'),
  getDetail: (id) => api.get(`/merchants/${id}/`),
  getPolicy: (merchantId) => api.get(`/policies/${merchantId}/`),
  updatePolicy: (merchantId, data) => api.patch(`/policies/${merchantId}/`, data),
};
