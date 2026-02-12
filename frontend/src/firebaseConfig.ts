/** Firebase Auth configuration — used only for sign-in (email + Google).
 *
 * No other Firebase services are used. After sign-in the ID token is sent
 * to the licensing server; the app then works offline with the Ed25519 key.
 */

import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, type Auth } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyADfsmLMp4qCKD8Sm1BIgKgYOjiK0F9z4A",
  authDomain: "promptshield-6d5cd.firebaseapp.com",
  projectId: "promptshield-6d5cd",
  storageBucket: "promptshield-6d5cd.firebasestorage.app",
  messagingSenderId: "455859748614",
  appId: "1:455859748614:web:7ace950d146b2be6156887",
};

const app = initializeApp(firebaseConfig);
export const auth: Auth = getAuth(app);

export const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({ prompt: "select_account" });
