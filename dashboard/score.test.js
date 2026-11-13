import assert from 'node:assert/strict';
import { test } from 'node:test';
import { WEIGHTS, baselineToMetrics, contributions, nextMetrics, riskLevel, riskScore } from './score.js';

const ALPHA = { latency_ms: 95, packet_loss_pct: 4.2, bandwidth_mbps: 45, cpu_pct: 78, temperature_celsius: 68 };

test('donne le même score que l’API pour le département Alpha', () => {
  // Valeurs renvoyées par POST /predict de api/main.py pour ces métriques.
  assert.equal(riskScore(ALPHA), 0.656);
  assert.deepEqual(contributions(ALPHA), {
    latence_reseau: 0.19, perte_paquets: 0.105, bande_passante: 0.164, charge_cpu: 0.117, temperature: 0.08,
  });
});

test('les poids somment à 1 et le score reste borné', () => {
  assert.ok(Math.abs(Object.values(WEIGHTS).reduce((a, b) => a + b, 0) - 1) < 1e-9);
  assert.equal(riskScore({ latency_ms: 0, packet_loss_pct: 0, bandwidth_mbps: 999, cpu_pct: 0, temperature_celsius: 0 }), 0.01);
  assert.equal(riskScore({ latency_ms: 9999, packet_loss_pct: 99, bandwidth_mbps: 0, cpu_pct: 100, temperature_celsius: 200 }), 0.99);
});

test('mêmes seuils de niveau que l’API', () => {
  assert.equal(riskLevel(0.71), 'CRITIQUE');
  assert.equal(riskLevel(0.7), 'MODERE');
  assert.equal(riskLevel(0.45), 'NORMAL');
});

test('la simulation revient vers la valeur de référence et reste dans les bornes', () => {
  const baseline = baselineToMetrics({ latency_ms: 28, packet_loss_pct: 0.8, bandwidth_mbps: 180, cpu_pct: 35, temp_celsius: 42 });
  let metrics = { ...baseline, latency_ms: 390, cpu_pct: 99 };
  for (let i = 0; i < 60; i += 1) metrics = nextMetrics(metrics, baseline, () => 0.5);
  assert.ok(Math.abs(metrics.latency_ms - 28) < 1);
  assert.ok(metrics.cpu_pct >= 1 && metrics.cpu_pct <= 100);
});
