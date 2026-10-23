import { QRCodeSVG } from 'qrcode.react';
import { mfaQrValue } from './mfa-qr-code';
import './mfa.css';

export default function MfaQrCode({ setup }) {
  const value = mfaQrValue(setup);
  if (!value) return <p className="mfa-qr-fallback" role="status">QR code indisponible. Vous pouvez utiliser la clé manuelle ci-dessous.</p>;
  return <figure className="mfa-enrollment-qr">
    <div className="mfa-qr-frame">
      <QRCodeSVG value={value} size={256} level="M" marginSize={4} bgColor="#ffffff" fgColor="#000000" title="QR code de configuration MFA CyberPME"/>
    </div>
    <figcaption>
      <strong>Scannez avec votre application d’authentification</strong>
      <span>Ajoutez un compte en scannant ce QR code, ou saisissez la clé ci-dessous.</span>
      <small>Ce QR code contient votre clé secrète. Ne le partagez pas. Il est généré sur votre appareil, sans service externe.</small>
    </figcaption>
  </figure>;
}
