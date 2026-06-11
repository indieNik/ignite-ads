import { initializeApp } from 'firebase/app';
import { GoogleAuthProvider, User, getAuth, onAuthStateChanged, signInWithPopup, signOut } from 'firebase/auth';

// Shared Firebase project with IgniteAI — same user accounts work on both apps.
export const firebaseConfig = {
  apiKey: 'AIzaSyDmvzFcgDYAN-4GzZBNVsYINYymGhw_4qc',
  authDomain: 'ignite-ai-01.firebaseapp.com',
  projectId: 'ignite-ai-01',
  storageBucket: 'ignite-ai-01.firebasestorage.app',
  messagingSenderId: '491013116254',
  appId: '1:491013116254:web:fb34bb1c311d308ea1ffcf',
};

export const API_URL = (window.location.hostname === 'localhost')
  ? 'http://localhost:8000'
  : 'https://ignite-ads-backend-928660012632.us-central1.run.app';

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);

export function watchUser(cb: (u: User | null) => void) {
  return onAuthStateChanged(auth, cb);
}

export function login() {
  return signInWithPopup(auth, new GoogleAuthProvider());
}

export function logout() {
  return signOut(auth);
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<any> {
  const token = await auth.currentUser?.getIdToken();
  const resp = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers || {}),
    },
  });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(body?.detail || `${resp.status} ${resp.statusText}`);
  }
  return body;
}
