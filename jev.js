import { experimental_evaluate as evaluate } from 'ai';

// Routed through Vercel AI Gateway; auth via AI_GATEWAY_API_KEY or VERCEL_OIDC_TOKEN in .env.local
const result = await evaluate({
  model: 'typesafe-ai/jev',
  state: 'I was charged twice. Please refund the duplicate.',
  questions: {
    requestsRefund: {
      type: 'boolean',
      instructions: 'Is the customer requesting money back?',
    },
  },
});

console.log(result.answers.requestsRefund.probability);
