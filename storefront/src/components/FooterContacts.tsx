import type { CSSProperties } from "react";

type ContactTone = "whatsapp" | "instagram" | "facebook";

const CONTACTS: { name: string; href: string; qr: string; tone: ContactTone }[] = [
  {
    name: "WhatsApp",
    href: "https://wa.me/our_blackmarket",
    qr: "/contact/whatsapp-qr.svg",
    tone: "whatsapp",
  },
  {
    name: "Instagram",
    href: "https://www.instagram.com/our_blackmarket/",
    qr: "/contact/instagram-qr.png",
    tone: "instagram",
  },
  {
    name: "Facebook",
    href: "https://www.facebook.com/people/Black-Market-TN/61594924482327/",
    qr: "/contact/facebook-qr.svg",
    tone: "facebook",
  },
];

function ContactMark({ tone }: { tone: ContactTone }) {
  return <img src={`/contact/${tone}.svg`} alt="" width="28" height="28" />;
}

export function FooterContacts() {
  return (
    <aside className="footer-contacts" aria-labelledby="footer-contact-title">
      <h2 id="footer-contact-title">Contact</h2>
      <div className="footer-contact-list">
        {CONTACTS.map((item, index) => (
          <a
            key={item.tone}
            className={`footer-contact is-${item.tone}`}
            href={item.href}
            target="_blank"
            rel="noopener noreferrer"
            style={{ "--i": index } as CSSProperties}
          >
            <span className="footer-contact-mark">
              <ContactMark tone={item.tone} />
            </span>
            <span className="footer-contact-copy">
              <strong>{item.name}</strong>
              <small>Scanner le code</small>
            </span>
            <img className="footer-contact-qr" src={item.qr} alt="" width="88" height="88" loading="lazy" />
          </a>
        ))}
      </div>
    </aside>
  );
}
