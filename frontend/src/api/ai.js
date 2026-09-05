import { api } from './client';

export const aiApi = {
  // Intent Recognition & Product Matching
  extractIntent: (message) => api.post('/ai/intent/', { message }),

  // Revenue Opportunities
  getOpportunities: (message, merchantId) =>
    api.post('/ai/opportunities/', { message, merchant_id: merchantId }),

  // Decision Engine
  getDecision: (message, merchantId) =>
    api.post('/ai/decision/', { message, merchant_id: merchantId }),

  // Buyer Profile
  createBuyerProfile: (profileData) => api.post('/ai/buyer/profiles/', profileData),

  // Negotiations — list can be filtered by merchant
  listNegotiations: (merchantId) => {
    const params = merchantId ? `?merchant_id=${merchantId}` : '';
    return api.get(`/ai/negotiations/${params}`);
  },
  getNegotiation: (id) => api.get(`/ai/negotiations/${id}/`),

  // Start negotiation: creates buyer profile + negotiation + runs it
  startNegotiation: async (merchantId, productId, buyerProfile) => {
    const budget = parseFloat(buyerProfile.budget) || 0;
    const sensitivity = (buyerProfile.price_sensitivity || 'HIGH').toUpperCase();
    const strategy = sensitivity === 'HIGH' ? 'VALUE_SEEKER' : sensitivity === 'LOW' ? 'FAST_BUYER' : 'BALANCED';
    const preferredPrice = buyerProfile.preferred_price ? parseFloat(buyerProfile.preferred_price) : parseFloat((budget * 0.85).toFixed(2));

    // Create buyer profile first
    const profile = await api.post('/ai/buyer/profiles/', {
      buyer_session_id: `buyer-session-${Date.now()}`,
      name: buyerProfile.name || 'Alex Kumar',
      budget_min: 0,
      budget_max: budget,
      preferred_price: preferredPrice,
      maximum_price: budget,
      walk_away_price: budget,
      strategy: strategy,
      negotiation_enabled: true,
      maximum_negotiation_rounds: 3,
      requirements: buyerProfile.productName ? [buyerProfile.productName] : [],
      price_sensitivity: buyerProfile.price_sensitivity || 'HIGH',
      loyalty_tier: buyerProfile.loyalty || 'NEW',
      merchant: merchantId,
      product: productId,
    });
    // Create negotiation session
    const session = await api.post('/ai/negotiations/', {
      buyer_profile_id: profile.id,
      merchant_id: merchantId,
      product_id: productId,
    });
    // Run negotiation
    const sessionId = session?.id || session?.negotiation_id;
    const result = await api.post(`/ai/negotiations/${sessionId}/run/`, { max_steps: 10 });
    return { session: { ...session, id: sessionId }, result };
  },

  // Initiate payment after negotiation is agreed
  initiatePayment: (negotiationId) =>
    api.post('/payments/transactions/', { negotiation_id: negotiationId }),
};
