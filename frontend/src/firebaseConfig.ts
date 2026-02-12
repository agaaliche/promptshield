/** Firebase configuration & initialization for PromptShield. */

import { initializeApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  OAuthProvider,
  type Auth,
} from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyADfsmLMp4qCKD8Sm1BIgKgYOjiK0F9z4A",
  authDomain: "promptshield-6d5cd.firebaseapp.com",
  projectId: "promptshield-6d5cd",
  storageBucket: "promptshield-6d5cd.firebasestorage.app",
  messagingSenderId: "455859748614",
  appId: "1:455859748614:web:7ace950d146b2be6156887",
  measurementId: "G-TGJZZ0XE3J",
};

const app = initializeApp(firebaseConfig);
export const auth: Auth = getAuth(app);

// ── Social providers ────────────────────────────────────────────
export const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({ prompt: "select_account" });

export const microsoftProvider = new OAuthProvider("microsoft.com");
microsoftProvider.setCustomParameters({ prompt: "select_account" });
