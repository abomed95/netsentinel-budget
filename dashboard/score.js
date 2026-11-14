/**
 * Score de risque — MÊME calcul que l'API (api/main.py).
 *
 * Le tableau de bord doit afficher exactement ce que l'API renverrait : les
 * poids et les normalisations sont donc recopiés ici, et un test vérifie que
 * les deux implémentations donnent le même résultat.
 */

export const WEIGHTS = {
  latence_reseau: 0.3,
  perte_paquets: 0.25,
  bande_passante: 0.2,
  charge_cpu: 0.15,
  temperature: 0.1,
};

export const FACTOR_LABELS = {
  latence_reseau: 'Latence réseau',
  perte_paquets: 'Perte de paquets',
  bande_passante: 'Bande passante',
  charge_cpu: 'Charge CPU',
  temperature: 'Température',
};

const clamp01 = (value) => Math.min(1, Math.max(0, value));
const round4 = (value) => Math.round(value * 10000) / 10000;

/** Part de chaque métrique dans son poids, entre 0 (sain) et 1 (saturé). */
export function normalize(metrics) {
  return {
    latence_reseau: clamp01(metrics.latency_ms / 150),
    perte_paquets: clamp01(metrics.packet_loss_pct / 10),
    bande_passante: clamp01(1 - metrics.bandwidth_mbps / 250),
    charge_cpu: clamp01(metrics.cpu_pct / 100),
    temperature: clamp01(metrics.temperature_celsius / 85),
  };
}

export function contributions(metrics) {
  const normalized = normalize(metrics);
  return Object.fromEntries(
    Object.keys(WEIGHTS).map((name) => [name, round4(WEIGHTS[name] * normalized[name])]),
  );
}

export function riskScore(metrics) {
  const total = Object.values(contributions(metrics)).reduce((sum, value) => sum + value, 0);
  return round4(Math.min(0.99, Math.max(0.01, total)));
}

export const LEVELS = {
  CRITIQUE: { label: 'Critique', recommendation: 'Intervention préventive immédiate recommandée' },
  MODERE: { label: 'Modéré', recommendation: 'Surveillance renforcée conseillée' },
  NORMAL: { label: 'Normal', recommendation: 'Aucune action requise — réseau stable' },
};

export function riskLevel(probability) {
  if (probability > 0.7) return 'CRITIQUE';
  if (probability > 0.45) return 'MODERE';
  return 'NORMAL';
}

/**
 * Mesure suivante d'un département : marche aléatoire qui revient vers sa
 * valeur de référence. Sans ce rappel, les métriques dériveraient sans fin et
 * tous les départements finiraient en alerte.
 */
export function nextMetrics(current, baseline, random = Math.random) {
  const step = (value, base, spread, min, max) => {
    const pull = (base - value) * 0.25;
    const noise = (random() - 0.5) * 2 * spread;
    return Math.min(max, Math.max(min, value + pull + noise));
  };
  return {
    latency_ms: step(current.latency_ms, baseline.latency_ms, 14, 1, 400),
    packet_loss_pct: step(current.packet_loss_pct, baseline.packet_loss_pct, 0.9, 0, 30),
    bandwidth_mbps: step(current.bandwidth_mbps, baseline.bandwidth_mbps, 16, 1, 1000),
    cpu_pct: step(current.cpu_pct, baseline.cpu_pct, 7, 1, 100),
    temperature_celsius: step(current.temperature_celsius, baseline.temperature_celsius, 3, 10, 110),
  };
}

/** Le fichier de référence nomme la température `temp_celsius` ; l'API, `temperature_celsius`. */
export function baselineToMetrics(baseline) {
  return {
    latency_ms: baseline.latency_ms,
    packet_loss_pct: baseline.packet_loss_pct,
    bandwidth_mbps: baseline.bandwidth_mbps,
    cpu_pct: baseline.cpu_pct,
    temperature_celsius: baseline.temp_celsius,
  };
}
