import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRightLeft,
  Boxes,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  ClipboardPaste,
  Copy,
  Edit3,
  Film,
  Globe2,
  PackagePlus,
  Plus,
  RefreshCw,
  Save,
  ShoppingBag,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  Trash2,
  Upload,
  Image as ImageIcon,
} from "lucide-react";
import { PageHeader, ActionButton, Modal, Field, Empty, FilterBar, useRemoteList } from "../admin-kit.jsx";
import { CATALOG_STATUS, dinars, dinarInput, catalogStatus, refreshLists } from "../site-format.jsx";

const DURATION_UNITS = [["days", "Jours"], ["months", "Mois"], ["years", "Années"]];
const DESCRIPTION_LIMIT = 8000;

function decimalInput(value) {
  return value || value === 0 ? String(value).replace(".", ",") : "";
}

function parseDecimal(value) {
  const number = Number(String(value || "").replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(number) ? number : 0;
}

function productForm(row, defaultServiceId) {
  return {
    service_id: String(row?.service_id || defaultServiceId || ""),
    name: row?.name || "",
    tn_price: dinarInput(row?.tn_price_millimes),
    site_category: row?.site_category || "",
    site_category_name: row?.site_category_name || "",
    site_badge: row?.site_badge || "",
    site_enabled: row ? row.site_enabled : true,
    site_featured: row?.site_featured || false,
    site_description_fr: row?.site_description_fr || "",
    site_remark: row?.site_remark || "",
    site_requires_info: Boolean(row?.site_requires_info),
    site_image_url: row?.site_image_url || "",
    site_video_url: row?.site_video_url || "",
    delivery_delay: row?.delivery_delay || "Instantané après confirmation",
    period_value: String(row?.period_value || 30),
    period_unit: row?.period_unit || "days",
    warranty_value: String(row?.warranty_value ?? 0),
    warranty_unit: row?.warranty_unit || "days",
    stock_mode: row?.unlimited_stock ? "unlimited" : "inventory",
    initial_inventory: "",
  };
}

function DurationInput({ value, unit, min, onValue, onUnit }) {
  return <div className="duration-input">
    <input type="number" min={min} value={value} onChange={(event) => onValue(event.target.value)} required />
    <select value={unit} onChange={(event) => onUnit(event.target.value)}>{DURATION_UNITS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select>
  </div>;
}

function ProductEditor({ row, services, rate, defaultServiceId, busy, onClose, onSave }) {
  const [form, setForm] = useState(() => productForm(row, defaultServiceId || services[0]?.id));
  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const creating = !row;
  const externallyStocked = Boolean(row?.supplier_provider || row?.manual_stock);
  const selectedService = services.find((service) => String(service.id) === String(form.service_id));
  const suggestedMillimes = Math.round((parseDecimal(row?.bot_price_usdt) * rate * 10)) * 100;
  const [image, setImage] = useState("");
  const [removeImage, setRemoveImage] = useState(false);
  const [imageError, setImageError] = useState("");
  const [video, setVideo] = useState("");
  const [removeVideo, setRemoveVideo] = useState(false);
  const [videoError, setVideoError] = useState("");
  const uploadedUrl = form.site_image_url.startsWith(OFFER_IMAGE_PATH) ? form.site_image_url : "";
  const serviceLogo = services.find((service) => String(service.id) === String(form.service_id))?.logo_url || "";
  const imagePreview = image || form.site_image_url;
  const videoPreview = video || form.site_video_url;
  const acceptImage = async (file) => {
    try {
      const data = await readImageFile(file, MAX_OFFER_IMAGE_BYTES);
      setImageError("");
      setImage(data);
      setRemoveImage(false);
    } catch (error) {
      setImageError(error.message);
    }
  };
  const pickImage = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void acceptImage(file);
  };
  const pasteImage = async () => {
    try {
      await acceptImage(await imageFromClipboard());
    } catch (error) {
      setImageError(error.message);
    }
  };
  const onPasteImage = (event) => {
    const file = fileFromPasteEvent(event);
    if (!file) return;
    event.preventDefault();
    void acceptImage(file);
  };
  const clearImage = () => { setImage(""); set("site_image_url", ""); setRemoveImage(true); };
  const acceptVideo = async (file) => {
    try {
      if (!VIDEO_TYPES.includes(file.type)) throw new Error("Format accepté : MP4 ou WebM.");
      if (file.size > MAX_VIDEO_BYTES) throw new Error("La vidéo doit peser moins de 8 Mo.");
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(new Error("Impossible de lire cette vidéo."));
        reader.readAsDataURL(file);
      });
      setVideoError("");
      setVideo(data);
      setRemoveVideo(false);
    } catch (error) {
      setVideoError(error.message);
    }
  };
  const pickVideo = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void acceptVideo(file);
  };
  const clearVideo = () => { setVideo(""); set("site_video_url", ""); setRemoveVideo(true); };
  const submit = (event) => {
    event.preventDefault();
    onSave({
      action: "site_offer_save",
      ...(row ? { offer_id: row.id } : {}),
      ...form,
      image,
      video,
      remove_image: removeImage ? "1" : "0",
      remove_video: removeVideo ? "1" : "0",
      site_enabled: form.site_enabled ? "1" : "0",
      site_featured: form.site_featured ? "1" : "0",
      site_requires_info: form.site_requires_info ? "1" : "0",
    });
  };
  return <Modal title={creating ? "Nouveau produit" : `${row.service_name} — ${row.name}`} onClose={onClose} wide>
    <form className="operation-form" onSubmit={submit}>
      <p>Le produit est le même que dans le bot, avec le même stock et le même fournisseur. Le nom, la description, la garantie, la durée et l’état enregistrés ici restent sur le site.</p>
      <h3 className="site-section-title">Produit</h3>
      <div className="form-grid">
        <Field label="Service">
          <select value={form.service_id} onChange={(event) => set("service_id", event.target.value)} required>
            {services.map((service) => <option key={service.id} value={service.id}>{service.emoji} {service.name}{service.active ? "" : " (désactivé)"}</option>)}
          </select>
          <small className="site-field-help">Changer le service déplace le produit dans cette catégorie sur le site.</small>
        </Field>
        {selectedService?.product_categories && <Field label="Nom de la catégorie">
          <input value={form.site_category_name} onChange={(event) => set("site_category_name", event.target.value)} maxLength={120} placeholder="Ex. ChatGPT, Google AI Pro" />
          <small className="site-field-help">Vide = le nom du produit. Ce nom est la catégorie affichée sur le site.</small>
        </Field>}
        <Field label="Nom du produit">
          <input value={form.name} onChange={(event) => set("name", event.target.value)} maxLength={120} required autoFocus={creating} placeholder="Ex. Netflix Premium 1 mois" />
        </Field>
        <Field label="Description en français" wide>
          <textarea
            className="site-description"
            value={form.site_description_fr}
            onChange={(event) => set("site_description_fr", event.target.value.slice(0, DESCRIPTION_LIMIT))}
            rows={14}
            placeholder={"Guide, conditions, liens…\nUn saut de ligne = une nouvelle ligne sur la fiche.\nUne ligne vide sépare les paragraphes."}
          />
          <small className={form.site_description_fr.length > DESCRIPTION_LIMIT * 0.9 ? "site-hint" : "site-field-help"}>
            {form.site_description_fr.length.toLocaleString("fr-FR")} / {DESCRIPTION_LIMIT.toLocaleString("fr-FR")} caractères. Les sauts de ligne et les liens https sont conservés.
          </small>
        </Field>
        <Field label="Image du produit (site, optionnel)" wide>
          <div className="site-logo-picker" tabIndex={0} onPaste={onPasteImage}>
            <span className="site-logo-preview">{imagePreview || serviceLogo ? <img src={imagePreview || serviceLogo} alt="Image du produit" /> : <ImageIcon size={18} />}</span>
            <label className="action-button secondary site-logo-upload"><Upload size={15} />{imagePreview ? "Remplacer" : "Importer une image"}<input type="file" accept={LOGO_TYPES.join(",")} onChange={pickImage} /></label>
            <ActionButton type="button" secondary icon={ClipboardPaste} onClick={pasteImage}>Coller direct</ActionButton>
            <label className="action-button secondary site-logo-upload"><Film size={15} />{videoPreview ? "Remplacer la vidéo" : "Ajouter une vidéo"}<input type="file" accept={VIDEO_TYPES.join(",")} onChange={pickVideo} /></label>
            {imagePreview && <ActionButton type="button" secondary danger icon={Trash2} onClick={clearImage}>Retirer</ActionButton>}
            {videoPreview && <ActionButton type="button" secondary danger icon={Trash2} onClick={clearVideo}>Retirer la vidéo</ActionButton>}
          </div>
          {videoPreview ? <video className="site-video-preview" src={videoPreview} controls playsInline preload="metadata" /> : null}
          {!image && !uploadedUrl && <input value={form.site_image_url} onChange={(event) => { set("site_image_url", event.target.value); setRemoveImage(false); }} type="url" maxLength={1000} placeholder="…ou collez un lien https://…/image.png" aria-label="Lien de l’image" />}
          {imageError ? <small className="site-hint"><AlertTriangle size={13} />{imageError}</small>
            : videoError ? <small className="site-hint"><AlertTriangle size={13} />{videoError}</small>
            : <small className="site-field-help">Image : PNG, JPEG ou WebP, 1 Mo max. Vidéo : MP4 ou WebM, 8 Mo max. L’image reste l’aperçu, la vidéo se joue sur la fiche. {imagePreview ? "Remplace le logo du service pour ce produit." : serviceLogo ? "Sans image, le logo du service est affiché." : "Sans image, l’emoji du service est affiché."}</small>}
        </Field>
      </div>
      <h3 className="site-section-title">Prix</h3>
      <div className="form-grid">
        <Field label="Prix sur le site (DT)">
          <input value={form.tn_price} onChange={(event) => set("tn_price", event.target.value)} inputMode="decimal" placeholder="Ex. 25,500" autoFocus={!creating} />
          {suggestedMillimes > 0 && <button type="button" className="site-link" onClick={() => set("tn_price", dinarInput(suggestedMillimes))}>Suggéré d’après le prix bot : {dinars(suggestedMillimes)}. Cela ne change pas le prix USDT.</button>}
        </Field>
        {!creating && <Field label="Prix bot (USDT, lecture seule)"><input value={decimalInput(row.bot_price_usdt)} disabled /></Field>}
      </div>
      <h3 className="site-section-title">Affichage sur le site</h3>
      <div className="form-grid">
        <Field label="Badge (optionnel)">
          <input value={form.site_badge} onChange={(event) => set("site_badge", event.target.value)} maxLength={48} placeholder="Ex. Promo, Nouveau, -20 %" />
        </Field>
        <Field label="Affichage">
          <label className="switch"><input type="checkbox" checked={form.site_enabled} onChange={(event) => set("site_enabled", event.target.checked)} /><span />Afficher sur le site</label>
        </Field>
        <Field label="Mise en avant">
          <label className="switch"><input type="checkbox" checked={form.site_featured} onChange={(event) => set("site_featured", event.target.checked)} /><span />Produit vedette</label>
        </Field>
        <Field label="Remarque (optionnel)" wide>
          <textarea value={form.site_remark} onChange={(event) => set("site_remark", event.target.value.slice(0, 400))} rows={3} maxLength={400} placeholder="Ex. Envoie l’email du compte à activer" />
          <small className="site-field-help">Écrite ici et affichée au client. Le client ne rédige pas cette remarque.</small>
        </Field>
        <Field label="Informations du client" wide>
          <label className="switch"><input type="checkbox" checked={form.site_requires_info} onChange={(event) => set("site_requires_info", event.target.checked)} /><span />Le client doit envoyer ses informations au paiement</label>
          <small className="site-field-help">Pour les produits qui ont besoin d’un email, d’un identifiant ou d’une précision. La remarque lui dit quoi envoyer.</small>
        </Field>
      </div>
      <h3 className="site-section-title">Livraison, durée et garantie</h3>
      <div className="form-grid">
        <Field label="Délai de livraison affiché sur le site">
          <input value={form.delivery_delay} onChange={(event) => set("delivery_delay", event.target.value)} maxLength={120} />
        </Field>
        <Field label="Durée de l’abonnement">
          <DurationInput value={form.period_value} unit={form.period_unit} min={1} onValue={(value) => set("period_value", value)} onUnit={(value) => set("period_unit", value)} />
        </Field>
        <Field label="Garantie (0 = sans garantie)">
          <DurationInput value={form.warranty_value} unit={form.warranty_unit} min={0} onValue={(value) => set("warranty_value", value)} onUnit={(value) => set("warranty_unit", value)} />
        </Field>
      </div>
      <h3 className="site-section-title">Stock</h3>
      <div className="form-grid">
        <Field label="Gestion du stock">
          {externallyStocked
            ? <input value={row.supplier_provider ? "Géré par le fournisseur API" : "Stock manuel (bot)"} disabled />
            : <select value={form.stock_mode} onChange={(event) => set("stock_mode", event.target.value)}>
              <option value="inventory">Comptes en stock (livrés un par un)</option>
              <option value="unlimited">Illimité (livraison manuelle)</option>
            </select>}
        </Field>
        {!creating && <Field label="Stock actuel"><input value={row.stock < 0 ? "Illimité" : String(row.stock)} disabled /></Field>}
        {creating && form.stock_mode === "inventory" && <Field label="Stock initial (optionnel)" wide>
          <textarea value={form.initial_inventory} onChange={(event) => set("initial_inventory", event.target.value)} rows={5} placeholder={"###\nEmail : compte1@exemple.com\nMot de passe : ••••\n###\nEmail : compte2@exemple.com\nMot de passe : ••••"} />
          <small className="site-field-help">Commencez chaque compte par une ligne ###. Vous pourrez en ajouter plus tard avec le bouton Stock.</small>
        </Field>}
      </div>
      {!form.tn_price && <p className="site-hint"><AlertTriangle size={14} />Sans prix en dinars, le produit reste masqué du site. Le bot garde son propre prix et son propre état.</p>}
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={onClose} disabled={busy}>Annuler</ActionButton><ActionButton type="submit" icon={creating ? Plus : Save} disabled={busy}>{busy ? "Enregistrement…" : creating ? "Créer le produit" : "Enregistrer"}</ActionButton></div>
    </form>
  </Modal>;
}

const LOGO_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_LOGO_BYTES = 500_000;
const MAX_OFFER_IMAGE_BYTES = 1_000_000;
const OFFER_IMAGE_PATH = "/api/storefront/offer-image";
const VIDEO_TYPES = ["video/mp4", "video/webm"];
const MAX_VIDEO_BYTES = 8_000_000;

function imageType(type) {
  return type === "image/jpg" ? "image/jpeg" : type;
}

function imageFileError(file, maxBytes) {
  if (!file) return "Aucune image dans le presse-papiers.";
  if (!LOGO_TYPES.includes(imageType(file.type))) return "Format accepté : PNG, JPEG ou WebP.";
  if (file.size > maxBytes) return maxBytes <= MAX_LOGO_BYTES ? "Le logo doit peser moins de 500 Ko." : "L’image doit peser moins de 1 Mo.";
  return "";
}

function readImageFile(file, maxBytes) {
  const error = imageFileError(file, maxBytes);
  if (error) return Promise.reject(new Error(error));
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Impossible de lire ce fichier."));
    reader.readAsDataURL(file);
  });
}

async function imageFromClipboard() {
  if (!navigator.clipboard?.read) throw new Error("Collez avec Ctrl+V dans la zone de l’image.");
  let items;
  try {
    items = await navigator.clipboard.read();
  } catch {
    throw new Error("Autorisez le collage, ou copiez l’image puis appuyez sur Ctrl+V.");
  }
  for (const item of items) {
    const type = ["image/png", "image/jpeg", "image/jpg", "image/webp"].find((entry) => item.types.includes(entry));
    if (!type) continue;
    const blob = await item.getType(type);
    return new File([blob], "collage", { type: imageType(type) });
  }
  throw new Error("Aucune image dans le presse-papiers.");
}

function fileFromPasteEvent(event) {
  const items = event.clipboardData?.items;
  if (!items) return null;
  for (const item of items) {
    if (item.kind === "file" && LOGO_TYPES.includes(imageType(item.type))) {
      const file = item.getAsFile();
      if (!file) return null;
      return file.type === imageType(file.type) ? file : new File([file], file.name || "collage", { type: imageType(file.type) });
    }
  }
  return null;
}

function MoveOffer({ row, services, onClose, onSave }) {
  const [serviceId, setServiceId] = useState(String(row.service_id || ""));
  const same = String(serviceId) === String(row.service_id);
  const submit = (event) => {
    event.preventDefault();
    if (same) return;
    onSave({ action: "site_offer_move", offer_id: row.id, service_id: serviceId });
  };
  return <Modal title={`Déplacer « ${row.name} »`} onClose={onClose}>
    <form className="operation-form" onSubmit={submit}>
      <Field label="Service de destination" wide>
        <select value={serviceId} onChange={(event) => setServiceId(event.target.value)} required>
          {services.map((service) => <option key={service.id} value={service.id}>{service.emoji} {service.name}</option>)}
        </select>
        <small className="site-field-help">Le produit prend la catégorie de ce service sur le site et dans le bot.</small>
      </Field>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={onClose}>Annuler</ActionButton><ActionButton type="submit" icon={ArrowRightLeft} disabled={same}>Déplacer</ActionButton></div>
    </form>
  </Modal>;
}

function CategoryRename({ group, onClose, onSave }) {
  const [name, setName] = useState(group.label || "");
  const [logo, setLogo] = useState("");
  const [removeLogo, setRemoveLogo] = useState(false);
  const [logoError, setLogoError] = useState("");
  const logoPreview = logo || (!removeLogo && group.logo_url) || "";
  const acceptLogo = async (file) => {
    try {
      const data = await readImageFile(file, MAX_LOGO_BYTES);
      setLogoError("");
      setLogo(data);
      setRemoveLogo(false);
    } catch (error) {
      setLogoError(error.message);
    }
  };
  const pickLogo = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void acceptLogo(file);
  };
  const pasteLogo = async () => {
    try {
      await acceptLogo(await imageFromClipboard());
    } catch (error) {
      setLogoError(error.message);
    }
  };
  const onPasteLogo = (event) => {
    const file = fileFromPasteEvent(event);
    if (!file) return;
    event.preventDefault();
    void acceptLogo(file);
  };
  const clearLogo = () => {
    setLogo("");
    setRemoveLogo(Boolean(group.logo_url));
    setLogoError("");
  };
  const submit = (event) => {
    event.preventDefault();
    onSave({
      action: "site_category_rename",
      name,
      offer_ids: (group.offer_ids || []).join(","),
      logo,
      remove_logo: removeLogo ? "1" : "0",
    });
  };
  return <Modal title={`Renommer « ${group.label} »`} onClose={onClose}>
    <form className="operation-form" onSubmit={submit}>
      <Field label="Nom de la catégorie sur le site" wide>
        <input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} required autoFocus placeholder="Ex. ChatGPT, Google AI Pro" />
      </Field>
      <Field label="Logo de la catégorie (site, optionnel)" wide>
        <div className="site-logo-picker" tabIndex={0} onPaste={onPasteLogo}>
          <span className="site-logo-preview">{logoPreview ? <img src={logoPreview} alt="Logo de la catégorie" /> : <ImageIcon size={18} />}</span>
          <label className="action-button secondary site-logo-upload"><Upload size={15} />{logoPreview ? "Remplacer" : "Importer un logo"}<input type="file" accept={LOGO_TYPES.join(",")} onChange={pickLogo} /></label>
          <ActionButton type="button" secondary icon={ClipboardPaste} onClick={pasteLogo}>Coller direct</ActionButton>
          {logoPreview && <ActionButton type="button" secondary danger icon={Trash2} onClick={clearLogo}>Retirer</ActionButton>}
        </div>
        {logoError ? <small className="site-hint"><AlertTriangle size={13} />{logoError}</small> : <small className="site-field-help">PNG, JPEG ou WebP, 500 Ko max. Collez une capture avec Coller direct ou Ctrl+V. Ce logo remplace l’emoji de la catégorie sur le site.</small>}
      </Field>
      <p>Ce nom s’affiche à la place du dossier d’origine. Pour déplacer un produit vers un autre service, ouvrez le produit et changez son service.</p>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={onClose}>Annuler</ActionButton><ActionButton type="submit" icon={Save}>Enregistrer</ActionButton></div>
    </form>
  </Modal>;
}

function ServiceEditor({ service, busy, onClose, onSave }) {
  const [form, setForm] = useState({
    name: service?.name || "",
    site_enabled: service ? service.site_enabled : true,
    logo: "",
    remove_logo: false,
  });
  const [logoError, setLogoError] = useState("");
  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const logoPreview = form.logo || (!form.remove_logo && service?.logo_url) || "";
  const acceptLogo = async (file) => {
    try {
      const data = await readImageFile(file, MAX_LOGO_BYTES);
      setLogoError("");
      setForm((current) => ({ ...current, logo: data, remove_logo: false }));
    } catch (error) {
      setLogoError(error.message);
    }
  };
  const pickLogo = (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void acceptLogo(file);
  };
  const pasteLogo = async () => {
    try {
      await acceptLogo(await imageFromClipboard());
    } catch (error) {
      setLogoError(error.message);
    }
  };
  const onPasteLogo = (event) => {
    const file = fileFromPasteEvent(event);
    if (!file) return;
    event.preventDefault();
    void acceptLogo(file);
  };
  const clearLogo = () => setForm((current) => ({ ...current, logo: "", remove_logo: Boolean(service?.logo_url) }));
  const submit = (event) => {
    event.preventDefault();
    onSave({
      action: "site_service_save",
      ...(service ? { service_id: service.id } : {}),
      ...form,
      site_enabled: form.site_enabled ? "1" : "0",
      remove_logo: form.remove_logo ? "1" : "0",
    });
  };
  return <Modal title={service ? `Modifier le service · ${service.name}` : "Nouveau service"} onClose={onClose}>
    <form className="operation-form" onSubmit={submit}>
      <p>Le nom enregistré ici est celui du site. Le nom et l’emoji du bot ne changent pas.</p>
      <div className="form-grid">
        <Field label="Nom sur le site"><input value={form.name} onChange={(event) => set("name", event.target.value)} maxLength={80} required autoFocus placeholder="Ex. Netflix" /></Field>
        <Field label="Logo du service (site, optionnel)" wide>
          <div className="site-logo-picker" tabIndex={0} onPaste={onPasteLogo}>
            <span className="site-logo-preview">{logoPreview ? <img src={logoPreview} alt="Logo du service" /> : service?.emoji || <ImageIcon size={18} />}</span>
            <label className="action-button secondary site-logo-upload"><Upload size={15} />{logoPreview ? "Remplacer" : "Importer un logo"}<input type="file" accept={LOGO_TYPES.join(",")} onChange={pickLogo} /></label>
            <ActionButton type="button" secondary icon={ClipboardPaste} onClick={pasteLogo}>Coller direct</ActionButton>
            {logoPreview && <ActionButton type="button" secondary danger icon={Trash2} onClick={clearLogo}>Retirer</ActionButton>}
          </div>
          {logoError ? <small className="site-hint"><AlertTriangle size={13} />{logoError}</small> : <small className="site-field-help">PNG, JPEG ou WebP, 500 Ko max. Collez une capture avec Coller direct ou Ctrl+V. Idéalement carré (256 × 256 px). Remplace l’emoji sur le site.</small>}
        </Field>
        <Field label="Affichage" wide><label className="switch"><input type="checkbox" checked={form.site_enabled} onChange={(event) => set("site_enabled", event.target.checked)} /><span />Afficher ce service sur le site</label></Field>
      </div>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={onClose} disabled={busy}>Annuler</ActionButton><ActionButton type="submit" icon={service ? Save : Plus} disabled={busy}>{busy ? "Enregistrement…" : service ? "Enregistrer" : "Créer le service"}</ActionButton></div>
    </form>
  </Modal>;
}

function StockEditor({ row, onClose, onSave }) {
  const [items, setItems] = useState("");
  return <Modal title={`Ajouter du stock · ${row.name}`} onClose={onClose}>
    <form className="operation-form" onSubmit={(event) => { event.preventDefault(); onSave({ action: "add_inventory", offer_id: row.id, items }); }}>
      <p>Stock actuel : <strong>{row.stock < 0 ? "illimité" : row.stock}</strong>. Chaque compte ajouté est livré automatiquement à un client (site ou bot), une seule fois.</p>
      <Field label="Comptes à ajouter" wide>
        <textarea value={items} onChange={(event) => setItems(event.target.value)} rows={9} required autoFocus placeholder={"###\nEmail : compte1@exemple.com\nMot de passe : ••••\n###\nEmail : compte2@exemple.com\nMot de passe : ••••"} />
        <small className="site-field-help">Commencez chaque compte par une ligne contenant uniquement ###. Le contenu est chiffré à l’enregistrement.</small>
      </Field>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={onClose}>Annuler</ActionButton><ActionButton type="submit" icon={PackagePlus}>Ajouter au stock</ActionButton></div>
    </form>
  </Modal>;
}

function DeleteConfirm({ target, onClose, onConfirm }) {
  const isService = target.type === "service";
  return <Modal title={isService ? "Supprimer le service" : "Supprimer le produit"} onClose={onClose}>
    <div className="operation-form">
      <p>Supprimer « <strong>{target.item.name}</strong> » ? {isService ? `Le service et ses ${target.item.offers} produit(s) disparaîtront du site et du bot.` : "Le produit disparaîtra du site et du bot."} Les commandes passées sont conservées.</p>
      <div className="dialog-actions"><ActionButton type="button" secondary onClick={onClose}>Annuler</ActionButton><ActionButton danger icon={Trash2} onClick={() => onConfirm(isService ? { action: "archive_service", service_id: target.item.id } : { action: "archive_offer", offer_id: target.item.id })}>Supprimer</ActionButton></div>
    </div>
  </Modal>;
}

export default function SiteCatalogPage({ onAction }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [serviceId, setServiceId] = useState("");
  const [category, setCategory] = useState("");
  const [collapsed, setCollapsed] = useState(() => new Set());
  const [editor, setEditor] = useState(null);
  const [saving, setSaving] = useState(false);
  const [result, loading] = useRemoteList("/admin/api/site-catalog", { search, status, service_id: serviceId });
  const counts = result.counts || {};
  const services = result.services || [];
  const groups = result.groups || [];
  const visibleGroups = category ? groups.filter((group) => group.id === category) : groups;
  const visibleCount = visibleGroups.reduce((total, group) => total + group.count, 0);
  useEffect(() => {
    if (category && !(result.groups || []).some((group) => group.id === category)) setCategory("");
  }, [category, result.groups]);
  const close = () => setEditor(null);
  const run = async (payload) => {
    if (saving) return null;
    setSaving(true);
    try {
      if (await onAction(payload)) { close(); refreshLists(); }
    } finally {
      setSaving(false);
    }
  };
  const toggleService = async (service) => {
    if (await onAction({ action: "site_service_visibility", service_id: service.id, site_enabled: service.site_enabled ? "0" : "1" })) refreshLists();
  };
  const toggleCollapse = (id) => setCollapsed((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const newProduct = () => setEditor(services.length ? { type: "product" } : { type: "service" });
  const renameGroup = (group) => {
    if (group.kind === "service") {
      const service = services.find((item) => item.id === group.service_id);
      if (service) setEditor({ type: "service", service });
      return;
    }
    setEditor({ type: "category", group });
  };
  const moveService = async (service, direction) => {
    const ids = services.map((item) => item.id);
    const index = ids.indexOf(service.id);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ids.length) return;
    const next = [...ids];
    const [moved] = next.splice(index, 1);
    next.splice(target, 0, moved);
    if (await onAction({ action: "site_reorder_catalog", ordered_ids: next.join(",") })) refreshLists();
  };
  const tabs = [["all", "Toutes"], ["on_sale", "En vente"], ["no_price", "Sans prix DT"], ["hidden", "Masquées"], ["disabled", "Désactivées"]];
  return <div className="operations-page site-page">
    <PageHeader
      title="Catalogue du site"
      description="Créez vos services et produits, fixez leur prix en dinars, gérez le stock et l’affichage sur ourblackmarket.com. Une offre sans prix DT reste masquée."
      actions={<>
        <ActionButton secondary icon={Plus} onClick={() => setEditor({ type: "service" })}>Nouveau service</ActionButton>
        <ActionButton icon={PackagePlus} onClick={newProduct}>Nouveau produit</ActionButton>
      </>}
    />
    <div className="site-tabs" role="tablist" aria-label="Filtrer les offres">
      {tabs.map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={status === value} onClick={() => setStatus(value)}>{label}<small>{counts[value] ?? 0}</small></button>)}
    </div>
    <div className="workspace-tabs" role="group" aria-label="Catégories du catalogue">
      <button type="button" aria-pressed={!category} onClick={() => setCategory("")}>Toutes les catégories</button>
      {groups.map((group) => <button key={group.id} type="button" aria-pressed={category === group.id} onClick={() => setCategory(group.id)}>{group.label}<small> {group.count}</small></button>)}
    </div>
    <FilterBar search={search} setSearch={setSearch} placeholder="Rechercher une offre ou un service…" resultCount={visibleCount}>
      <select value={serviceId} onChange={(event) => setServiceId(event.target.value)} aria-label="Service">
        <option value="">Tous les services</option>
        {services.map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}
      </select>
    </FilterBar>
    {loading && !groups.length ? <div className="operation-loading"><RefreshCw className="spin" />Chargement du catalogue…</div>
      : !visibleGroups.length ? <Empty icon={ShoppingBag} title="Aucune offre" text={counts.all ? "Aucune offre ne correspond à ce filtre." : "Créez un service puis ajoutez votre premier produit."} />
      : <div className="catalog-react-grid catalog-table-template catalog-list-view site-catalog-groups" aria-busy={loading}>
        {visibleGroups.map((group) => {
          const folded = collapsed.has(group.id);
          return <section key={group.id} className={`data-panel catalog-collection ${folded ? "collapsed" : ""}`}>
            <header className="panel-heading catalog-collection-heading">
              <div className="catalog-collection-title">
                <button type="button" className="catalog-collection-toggle" onClick={() => toggleCollapse(group.id)} aria-expanded={!folded} aria-label={`${folded ? "Déplier" : "Replier"} ${group.label}`}><ChevronRight size={16} /></button>
                {group.logo_url ? <img className="site-thumb" src={group.logo_url} alt="" /> : null}
                <div>
                  <span className="eyebrow">Catégorie · {group.count} produit(s) · {group.on_sale} en vente</span>
                  <h2>{group.label}</h2>
                </div>
                <button type="button" className="action-button secondary catalog-rename" onClick={() => renameGroup(group)}>Renommer</button>
              </div>
            </header>
            <div className="catalog-offers">
              <div className="catalog-offers-content">
                <div className="responsive-table">
                  <table className="catalog-offer-table site-catalog-table">
                    <thead><tr><th>Produit</th><th>Prix bot</th><th>Prix site</th><th>Stock</th><th>Statut</th><th>Actif</th><th className="catalog-col-actions" aria-label="Actions" /></tr></thead>
                    <tbody>{group.items.map((row) => {
                      const [label, className] = CATALOG_STATUS[catalogStatus(row)];
                      const enabled = row.site_enabled && row.service_visible;
                      const canStock = !row.unlimited_stock && !row.supplier_provider && !row.manual_stock;
                      return <tr key={row.id} className={`offer-row ${enabled ? "" : "inactive"}`}>
                        <td className="catalog-col-name"><div className="site-offer-cell">
                          {row.site_image_url || row.category_logo_url || row.service_logo_url ? <img className="site-thumb" src={row.site_image_url || row.category_logo_url || row.service_logo_url} alt="" loading="lazy" /> : <span className="site-thumb">{row.service_emoji || <ShoppingBag size={15} />}</span>}
                          <div><strong>{row.name}</strong><small>{row.service_name}{row.site_featured && <em className="site-chip"><Sparkles size={11} />Vedette</em>}{row.site_badge && <em className="site-chip">{row.site_badge}</em>}</small></div>
                        </div></td>
                        <td>{row.bot_price_usdt} USDT</td>
                        <td className="catalog-col-price">{row.tn_price_millimes ? <strong>{dinars(row.tn_price_millimes)}</strong> : <small>Suggestion {dinars(row.suggested_price_millimes)}</small>}</td>
                        <td>{row.stock < 0 ? "∞" : row.stock}</td>
                        <td><span className={`status ${className}`}>{label}</span>{!row.service_visible && <small>Service masqué</small>}</td>
                        <td><span className={`status ${enabled ? "delivered" : "cancelled"}`}>{enabled ? "Sur le site" : "Masqué"}</span></td>
                        <td className="catalog-col-actions"><div className="site-row-actions">
                          <ActionButton secondary icon={Edit3} onClick={() => setEditor({ type: "product", row })}>{row.tn_price_millimes ? "Modifier" : "Fixer le prix"}</ActionButton>
                          <button type="button" title="Déplacer" aria-label={`Déplacer ${row.name}`} onClick={() => setEditor({ type: "move", row })}><ArrowRightLeft size={15} /></button>
                          {canStock && <button type="button" title="Ajouter du stock" aria-label={`Ajouter du stock à ${row.name}`} onClick={() => setEditor({ type: "stock", row })}><Boxes size={15} /></button>}
                          <button type="button" title="Dupliquer" aria-label={`Dupliquer ${row.name}`} onClick={() => run({ action: "duplicate_offer", offer_id: row.id })}><Copy size={15} /></button>
                          <button type="button" title={row.site_enabled ? "Masquer sur le site" : "Afficher sur le site"} aria-label={`${row.site_enabled ? "Masquer" : "Afficher"} ${row.name} sur le site`} onClick={() => run({ action: "site_offer_visibility", offer_id: row.id, site_enabled: row.site_enabled ? "0" : "1" })}>{row.site_enabled ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}</button>
                          <button type="button" className="danger" title="Supprimer" aria-label={`Supprimer ${row.name}`} onClick={() => setEditor({ type: "delete", target: { type: "offer", item: row } })}><Trash2 size={15} /></button>
                        </div></td>
                      </tr>;
                    })}</tbody>
                  </table>
                </div>
              </div>
            </div>
          </section>;
        })}
      </div>}
    <section className="site-panel">
      <header><h3><Globe2 size={17} />Services</h3><small>Le nom du service est la catégorie du site. Les flèches changent l’ordre sur le site.</small></header>
      {!services.length ? <Empty icon={Globe2} title="Aucun service" text="Créez un premier service pour y ranger vos produits." />
        : <div className="site-service-grid">{services.map((service) => <div key={service.id} className={`site-service${service.site_enabled ? "" : " site-row-disabled"}`}>
          {service.logo_url ? <img className="site-thumb" src={service.logo_url} alt="" loading="lazy" /> : <span className="site-thumb">{service.emoji || <Globe2 size={15} />}</span>}
          <span><strong title={service.name}>{service.name}</strong><small>{service.site_enabled ? `${service.on_sale}/${service.offers} en vente` : "Masqué sur le site"}</small></span>
          <span className="site-row-actions">
            <button type="button" title="Monter" aria-label={`Monter ${service.name}`} disabled={services[0]?.id === service.id} onClick={() => moveService(service, -1)}><ChevronUp size={15} /></button>
            <button type="button" title="Descendre" aria-label={`Descendre ${service.name}`} disabled={services.at(-1)?.id === service.id} onClick={() => moveService(service, 1)}><ChevronDown size={15} /></button>
            <button type="button" title="Ajouter un produit" aria-label={`Ajouter un produit à ${service.name}`} onClick={() => setEditor({ type: "product", serviceId: service.id })}><Plus size={15} /></button>
            <button type="button" title="Modifier" aria-label={`Modifier ${service.name}`} onClick={() => setEditor({ type: "service", service })}><Edit3 size={15} /></button>
            <button type="button" className="danger" title="Supprimer" aria-label={`Supprimer ${service.name}`} onClick={() => setEditor({ type: "delete", target: { type: "service", item: service } })}><Trash2 size={15} /></button>
            <label className="switch" title="Afficher sur le site"><input type="checkbox" checked={service.site_enabled} onChange={() => toggleService(service)} aria-label={`Afficher ${service.name} sur le site`} /><span /></label>
          </span>
        </div>)}</div>}
    </section>
    {editor?.type === "product" && <ProductEditor row={editor.row} services={services} rate={Number(result.tnd_per_usdt) || 0} defaultServiceId={editor.serviceId || (serviceId ? Number(serviceId) : null)} busy={saving} onClose={close} onSave={run} />}
    {editor?.type === "service" && <ServiceEditor service={editor.service} busy={saving} onClose={close} onSave={run} />}
    {editor?.type === "category" && <CategoryRename group={editor.group} onClose={close} onSave={run} />}
    {editor?.type === "move" && <MoveOffer row={editor.row} services={services} onClose={close} onSave={run} />}
    {editor?.type === "stock" && <StockEditor row={editor.row} onClose={close} onSave={run} />}
    {editor?.type === "delete" && <DeleteConfirm target={editor.target} onClose={close} onConfirm={run} />}
  </div>;
}
