import { NextRequest, NextResponse } from "next/server";
import Stripe from "stripe";

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || "", {
  apiVersion: "2025-02-24.acacia",
});

const WEBHOOK_SECRET = process.env.STRIPE_WEBHOOK_SECRET || "";
const LICENSING_URL = process.env.LICENSING_SERVER_URL || "https://licensing-server-455859748614.us-east4.run.app";
const LICENSING_INTERNAL_KEY = process.env.LICENSING_INTERNAL_KEY || "";

export async function POST(req: NextRequest) {
  const body = await req.text();
  const signature = req.headers.get("stripe-signature") || "";

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, signature, WEBHOOK_SECRET);
  } catch (err: unknown) {
    console.error("Webhook signature verification failed:", err);
    return NextResponse.json({ error: "Invalid signature" }, { status: 400 });
  }

  try {
    switch (event.type) {
      case "checkout.session.completed": {
        const session = event.data.object as Stripe.Checkout.Session;
        const firebaseUid = session.metadata?.firebase_uid;
        if (firebaseUid) {
          // Upgrade user on licensing server
          await fetch(`${LICENSING_URL}/admin/upgrade`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Internal-Key": LICENSING_INTERNAL_KEY,
            },
            body: JSON.stringify({
              firebase_uid: firebaseUid,
              plan: "pro",
              stripe_customer_id: session.customer,
              stripe_subscription_id: session.subscription,
            }),
          });
        }
        break;
      }

      case "customer.subscription.deleted": {
        const sub = event.data.object as Stripe.Subscription;
        const customer = await stripe.customers.retrieve(
          sub.customer as string
        );
        if ("metadata" in customer && customer.metadata?.firebase_uid) {
          // Downgrade user on licensing server
          await fetch(`${LICENSING_URL}/admin/downgrade`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Internal-Key": LICENSING_INTERNAL_KEY,
            },
            body: JSON.stringify({
              firebase_uid: customer.metadata.firebase_uid,
              plan: "free_trial",
            }),
          });
        }
        break;
      }

      case "invoice.payment_failed": {
        const invoice = event.data.object as Stripe.Invoice;
        console.warn("Payment failed for customer:", invoice.customer);
        break;
      }
    }
  } catch (err) {
    console.error("Webhook handler error:", err);
  }

  return NextResponse.json({ received: true });
}
