import { loadStripe } from "@stripe/stripe-js";

const stripePromise = loadStripe(
  process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY || ""
);

export async function redirectToCheckout(sessionId: string) {
  const stripe = await stripePromise;
  if (!stripe) throw new Error("Stripe not loaded");
  const { error } = await stripe.redirectToCheckout({ sessionId });
  if (error) throw error;
}

export { stripePromise };
