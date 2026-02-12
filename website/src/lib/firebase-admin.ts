import * as admin from "firebase-admin";

if (!admin.apps.length) {
  // In production, use GOOGLE_APPLICATION_CREDENTIALS env var
  // or a service account JSON
  const serviceAccount = process.env.FIREBASE_SERVICE_ACCOUNT_KEY
    ? JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT_KEY)
    : undefined;

  admin.initializeApp({
    credential: serviceAccount
      ? admin.credential.cert(serviceAccount)
      : admin.credential.applicationDefault(),
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || "promptshield-6d5cd",
  });
}

export default admin;
