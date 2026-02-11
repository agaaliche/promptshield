"""One-time Ed25519 keypair generator.

Run this script ONCE to generate the signing keypair:
    python generate_keys.py

Then set the output values as environment variables:
    PS_ED25519_PRIVATE_KEY_B64=...
    PS_ED25519_PUBLIC_KEY_B64=...

The PUBLIC key also needs to be embedded in the Tauri Rust binary
(see frontend/src-tauri/src/license.rs — ED25519_PUBLIC_KEY_B64).
"""

from crypto import generate_keypair


def main() -> None:
    priv_b64, pub_b64 = generate_keypair()
    print("=" * 60)
    print("Ed25519 KEYPAIR GENERATED — STORE SECURELY")
    print("=" * 60)
    print()
    print("PRIVATE KEY (server .env only — NEVER ship in app):")
    print(f"  PS_ED25519_PRIVATE_KEY_B64={priv_b64}")
    print()
    print("PUBLIC KEY (embed in Rust binary + server .env):")
    print(f"  PS_ED25519_PUBLIC_KEY_B64={pub_b64}")
    print()
    print("Rust constant (paste into license.rs):")
    print(f'  const ED25519_PUBLIC_KEY_B64: &str = "{pub_b64}";')
    print("=" * 60)


if __name__ == "__main__":
    main()
