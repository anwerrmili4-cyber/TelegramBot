import { Resend } from 'resend';

const apiKey = process.env.RESEND_API_KEY;
if (!apiKey || apiKey === 're_xxxxxxxxx') {
  console.error('Set RESEND_API_KEY in .env to your real Resend API key.');
  process.exit(1);
}

const resend = new Resend(apiKey);

const { data, error } = await resend.emails.send({
  from: 'onboarding@resend.dev',
  to: 'anwerrmili7@gmail.com',
  subject: 'Hello World',
  html: '<p>Congrats on sending your <strong>first email</strong>!</p>',
});

if (error) {
  console.error('Failed to send email:', error);
  process.exit(1);
}

console.log('Email sent:', data.id);
