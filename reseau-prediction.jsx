/**
 * NetSentinel — tableau de bord de prédiction de coupures réseau H+1.
 *
 * Quatre onglets, ceux que décrit le README : tableau de bord, prédiction H+1,
 * alertes, rapport. Les mesures sont SIMULÉES à partir du fichier de référence
 * (data/arcep_sample.json) ; le score est celui de l'API, recalculé à
 * l'identique dans dashboard/score.js.
 */
import { Component, useEffect, useId, useMemo, useRef, useState } from 'react';
import sample from './data/arcep_sample.json';
import {
  FACTOR_LABELS,
  LEVELS,
  WEIGHTS,
  baselineToMetrics,
  contributions,
  nextMetrics,
  normalize,
  riskLevel,
  riskScore,
} from './dashboard/score.js';
import './dashboard/netsentinel.css';

const REFRESH_MS = 5000;
const HISTORY_POINTS = 24;
const MAX_ALERTS = 60;

const TABS = [
  { id: 'dashboard', label: 'Tableau de bord' },
  { id: 'prediction', label: 'Prédiction H+1' },
  { id: 'alerts', label: 'Alertes' },
  { id: 'report', label: 'Rapport Ministre' },
];

const percent = (value) => `${Math.round(value * 100)} %`;
const number = (value, digits = 0) =>
  value.toLocaleString('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
const euros = (value) =>
  value.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });
const clock = (date) => date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

/* ── Icônes de statut : la couleur n'est jamais seule à porter l'information ── */
function LevelIcon({ level }) {
  if (level === 'CRITIQUE') {
    return (
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <path d="M8 1.5 15 14H1L8 1.5Z" fill="currentColor" />
        <path d="M8 6v4" stroke="var(--surface)" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="8" cy="12" r="0.9" fill="var(--surface)" />
      </svg>
    );
  }
  if (level === 'MODERE') {
    return (
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="8" cy="8" r="6.5" fill="currentColor" />
        <path d="M8 4.5v4" stroke="var(--surface)" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="8" cy="11" r="0.9" fill="var(--surface)" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" fill="currentColor" />
      <path d="m5 8.2 2 2 4-4.2" fill="none" stroke="var(--surface)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function LevelBadge({ level }) {
  return (
    <span className={`ns-badge ${level}`}>
      <LevelIcon level={level} />
      {LEVELS[level].label}
    </span>
  );
}

const LEVEL_COLOR = { NORMAL: 'var(--good)', MODERE: 'var(--warning)', CRITIQUE: 'var(--critical)' };

/* ── Courbe d'évolution, avec lecture de la valeur au survol ou au doigt ── */
function Sparkline({ points, label, height = 72 }) {
  const [hover, setHover] = useState(null);
  // Le dessin prend la largeur RÉELLE de son conteneur (1 unité = 1 pixel) : un
  // viewBox fixe étiré grossissait ou rapetissait le texte selon la carte.
  const box = useRef(null);
  const [width, setWidth] = useState(300);
  useEffect(() => {
    if (!box.current || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(120, Math.round(entry.contentRect.width))));
    observer.observe(box.current);
    return () => observer.disconnect();
  }, []);
  const x = (index) => (points.length > 1 ? (index / (points.length - 1)) * width : width);
  const y = (value) => height - value * height;
  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const area = `${line} L${x(points.length - 1).toFixed(1)},${height} L0,${height} Z`;

  function track(event) {
    const box = event.currentTarget.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    setHover(Math.round(ratio * (points.length - 1)));
  }

  const active = hover != null ? points[hover] : null;
  return (
    <div ref={box} className="ns-chart" onPointerMove={track} onPointerDown={track} onPointerLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
        {/* Seuil d'alerte critique : la seule référence utile sur cette courbe. */}
        <line className="ns-threshold" x1="0" x2={width} y1={y(0.7)} y2={y(0.7)} />
        <text className="ns-axis-text" x={width} y={y(0.7) - 4} textAnchor="end">seuil critique 70 %</text>
        <path className="ns-spark-area" d={area} />
        <path className="ns-spark-line" d={line} />
        {active ? (
          <>
            <line className="ns-crosshair" x1={x(hover)} x2={x(hover)} y1="0" y2={height} />
            <circle className="ns-point" cx={x(hover)} cy={y(active.value)} r="4.5" />
          </>
        ) : (
          <circle className="ns-point" cx={x(points.length - 1)} cy={y(points[points.length - 1].value)} r="4" />
        )}
      </svg>
      {active ? (
        <div className="ns-tooltip" style={{ left: `${(x(hover) / width) * 100}%` }}>
          {clock(active.at)} · {percent(active.value)}
        </div>
      ) : null}
    </div>
  );
}

/* ── Jauge : un seul chiffre, la probabilité de coupure ── */
function Gauge({ value, level }) {
  const radius = 80;
  const length = Math.PI * radius;
  return (
    <div className="ns-gauge-wrap">
      <svg viewBox="0 0 200 112" role="img" aria-label={`Probabilité de coupure : ${percent(value)}`}>
        <path className="ns-gauge-track" d="M20 100 A80 80 0 0 1 180 100" />
        <path
          className="ns-gauge-fill"
          d="M20 100 A80 80 0 0 1 180 100"
          stroke={LEVEL_COLOR[level]}
          strokeDasharray={length}
          strokeDashoffset={length * (1 - value)}
        />
      </svg>
      <div className="ns-gauge-value">{percent(value)}</div>
      <p className="ns-gauge-caption">Probabilité de coupure dans les 60 minutes</p>
      <LevelBadge level={level} />
    </div>
  );
}

/* ── Radar : profil des cinq métriques, chacune ramenée entre 0 et 1 ── */
function Radar({ values }) {
  const names = Object.keys(values);
  // Zone de dessin plus large que haute : les libellés de gauche et de droite
  // (« Température », « Perte de paquets ») ont besoin de place pour ne pas être coupés.
  const cx = 170;
  const cy = 112;
  const radius = 76;
  const point = (index, scale) => {
    const angle = (Math.PI * 2 * index) / names.length - Math.PI / 2;
    return [cx + Math.cos(angle) * radius * scale, cy + Math.sin(angle) * radius * scale];
  };
  const ring = (scale) => names.map((_, i) => point(i, scale).map((n) => n.toFixed(1)).join(',')).join(' ');
  const shape = names.map((name, i) => point(i, Math.max(0.04, values[name])).map((n) => n.toFixed(1)).join(',')).join(' ');

  return (
    <svg className="ns-radar" viewBox="0 0 340 224" role="img" aria-label="Profil des cinq métriques, de 0 (sain) à 1 (saturé)">
      {[0.25, 0.5, 0.75, 1].map((scale) => (
        <polygon key={scale} className="ns-radar-grid" points={ring(scale)} />
      ))}
      <polygon className="ns-radar-shape" points={shape} />
      {names.map((name, i) => {
        const [lx, ly] = point(i, 1.14);
        // Le libellé s'écarte du centre : aligné à gauche à droite du radar, et inversement.
        const anchor = Math.abs(lx - cx) < 4 ? 'middle' : lx > cx ? 'start' : 'end';
        return (
          <text key={name} className="ns-axis-text ns-radar-label" x={lx} y={ly} textAnchor={anchor} dominantBaseline="middle">
            {FACTOR_LABELS[name]}
          </text>
        );
      })}
    </svg>
  );
}

function Bars({ values }) {
  const max = Math.max(...Object.values(WEIGHTS));
  return (
    <div className="ns-bars">
      {Object.entries(values)
        .sort((a, b) => b[1] - a[1])
        .map(([name, value]) => (
          <div className="ns-bar-row" key={name} title={`${FACTOR_LABELS[name]} : ${number(value * 100, 1)} points sur ${number(WEIGHTS[name] * 100)} possibles`}>
            <span>{FACTOR_LABELS[name]}</span>
            <span>+{number(value * 100, 1)} pts</span>
            <div className="ns-bar-track">
              <div className="ns-bar-fill" style={{ width: `${(value / max) * 100}%` }} />
            </div>
          </div>
        ))}
    </div>
  );
}

/* ── Simulation des mesures ── */
function useNetwork() {
  const [state, setState] = useState(null);

  useEffect(() => {
    const now = new Date();
    const initial = sample.departments.map((dept) => {
      const baseline = baselineToMetrics(dept.baseline);
      // Historique de départ : on fait tourner la simulation « à blanc » pour
      // que les courbes ne commencent pas vides.
      let metrics = baseline;
      const history = [];
      for (let i = HISTORY_POINTS - 1; i >= 0; i -= 1) {
        metrics = nextMetrics(metrics, baseline);
        history.push({ at: new Date(now.getTime() - i * REFRESH_MS), value: riskScore(metrics) });
      }
      return { id: dept.id, name: dept.name, region: dept.region, baseline, metrics, history, incidents: dept.incidents_2025 };
    });
    setState({ departments: initial, alerts: [], updatedAt: now });

    const timer = setInterval(() => {
      setState((previous) => {
        if (!previous) return previous;
        const at = new Date();
        const alerts = [];
        const departments = previous.departments.map((dept) => {
          const metrics = nextMetrics(dept.metrics, dept.baseline);
          const value = riskScore(metrics);
          const before = riskLevel(dept.history[dept.history.length - 1].value);
          const after = riskLevel(value);
          // Une alerte par CHANGEMENT de niveau, pas par mesure : sinon le
          // journal se remplit de répétitions et plus personne ne le lit.
          if (after !== before) {
            alerts.push({ id: `${dept.id}-${at.getTime()}`, at, department: dept.name, level: after, from: before, value });
          }
          return { ...dept, metrics, history: [...dept.history.slice(1 - HISTORY_POINTS), { at, value }] };
        });
        return { departments, alerts: [...alerts, ...previous.alerts].slice(0, MAX_ALERTS), updatedAt: at };
      });
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, []);

  return state;
}

/* ── Onglet 1 : tableau de bord ── */
function DashboardTab({ departments, onOpen }) {
  const scores = departments.map((d) => d.history[d.history.length - 1].value);
  const levels = scores.map(riskLevel);
  const average = scores.reduce((sum, value) => sum + value, 0) / scores.length;
  const critical = levels.filter((l) => l === 'CRITIQUE').length;
  const moderate = levels.filter((l) => l === 'MODERE').length;

  return (
    <>
      <h2 className="ns-title">Vue d’ensemble du réseau</h2>
      <p className="ns-lede">État des {departments.length} départements pilotes, actualisé toutes les 5 secondes.</p>

      <div className="ns-section ns-grid cols-3">
        <div className="ns-card">
          <p className="ns-tile-label">Départements en alerte critique</p>
          <p className="ns-tile-value">{critical}</p>
          <p className="ns-tile-sub">{moderate} sous surveillance renforcée</p>
        </div>
        <div className="ns-card">
          <p className="ns-tile-label">Risque moyen à H+1</p>
          <p className="ns-tile-value">{percent(average)}</p>
          <p className="ns-tile-sub">sur l’ensemble des départements</p>
        </div>
        <div className="ns-card">
          <p className="ns-tile-label">Départements stables</p>
          <p className="ns-tile-value">{levels.filter((l) => l === 'NORMAL').length}</p>
          <p className="ns-tile-sub">aucune action requise</p>
        </div>
      </div>

      <section className="ns-section" aria-label="Départements">
        <div className="ns-grid cards">
          {departments.map((dept, index) => (
            <button key={dept.id} type="button" className="ns-card ns-dept" onClick={() => onOpen(dept.id)}>
              <div className="ns-dept-head">
                <div>
                  <p className="ns-dept-name">{dept.name}</p>
                  <p className="ns-dept-region">Région {dept.region}</p>
                </div>
                <LevelBadge level={levels[index]} />
              </div>
              <p className="ns-dept-prob">
                {percent(scores[index])} <small>de risque à H+1</small>
              </p>
              <Sparkline points={dept.history} label={`Évolution du risque — ${dept.name}`} />
              <dl className="ns-metrics">
                <div className="ns-metric"><dt>Latence</dt><dd>{number(dept.metrics.latency_ms)} ms</dd></div>
                <div className="ns-metric"><dt>Pertes</dt><dd>{number(dept.metrics.packet_loss_pct, 1)} %</dd></div>
                <div className="ns-metric"><dt>Débit</dt><dd>{number(dept.metrics.bandwidth_mbps)} Mb/s</dd></div>
                <div className="ns-metric"><dt>CPU</dt><dd>{number(dept.metrics.cpu_pct)} %</dd></div>
              </dl>
            </button>
          ))}
        </div>
      </section>
    </>
  );
}

/* ── Onglet 2 : prédiction H+1 ── */
function PredictionTab({ departments, selected, onSelect }) {
  const selectId = useId();
  const dept = departments.find((d) => d.id === selected) ?? departments[0];
  const value = riskScore(dept.metrics);
  const level = riskLevel(value);

  return (
    <>
      <h2 className="ns-title">Prédiction à une heure</h2>
      <p className="ns-lede">Probabilité de coupure dans les 60 prochaines minutes et facteurs qui la composent.</p>

      <div className="ns-toolbar">
        <label className="ns-field-label" htmlFor={selectId}>Département</label>
        <select id={selectId} className="ns-select" value={dept.id} onChange={(event) => onSelect(event.target.value)}>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>{d.name} — {d.region}</option>
          ))}
        </select>
      </div>

      <div className="ns-section ns-grid cols-2">
        <div className="ns-card">
          <Gauge value={value} level={level} />
          <p className="ns-note" style={{ textAlign: 'center' }}>{LEVELS[level].recommendation}</p>
        </div>
        <div className="ns-card">
          <h3 className="ns-h2">Profil des métriques</h3>
          <Radar values={normalize(dept.metrics)} />
        </div>
      </div>

      <div className="ns-section ns-grid cols-2">
        <div className="ns-card">
          <h3 className="ns-h2">Contributions au score</h3>
          <Bars values={contributions(dept.metrics)} />
          <p className="ns-note">
            Part de chaque métrique dans le score, en points de pourcentage. Pondération fixe du
            prototype : ce ne sont pas des valeurs SHAP issues d’un modèle entraîné.
          </p>
        </div>
        <div className="ns-card">
          <h3 className="ns-h2">Évolution sur les deux dernières minutes</h3>
          <Sparkline points={dept.history} label={`Évolution du risque — ${dept.name}`} height={110} />
          <dl className="ns-metrics stack">
            <div className="ns-metric"><dt>Latence</dt><dd>{number(dept.metrics.latency_ms)} ms</dd></div>
            <div className="ns-metric"><dt>Pertes de paquets</dt><dd>{number(dept.metrics.packet_loss_pct, 1)} %</dd></div>
            <div className="ns-metric"><dt>Bande passante</dt><dd>{number(dept.metrics.bandwidth_mbps)} Mb/s</dd></div>
            <div className="ns-metric"><dt>CPU routeur</dt><dd>{number(dept.metrics.cpu_pct)} %</dd></div>
            <div className="ns-metric"><dt>Température</dt><dd>{number(dept.metrics.temperature_celsius)} °C</dd></div>
          </dl>
        </div>
      </div>
    </>
  );
}

/* ── Onglet 3 : alertes ── */
function AlertsTab({ alerts }) {
  const [filter, setFilter] = useState('ALL');
  const filterId = useId();
  const visible = filter === 'ALL' ? alerts : alerts.filter((a) => a.level === filter);

  return (
    <>
      <h2 className="ns-title">Journal des alertes</h2>
      <p className="ns-lede">Une ligne à chaque changement de niveau d’un département, la plus récente en premier.</p>

      <div className="ns-toolbar">
        <label className="ns-field-label" htmlFor={filterId}>Niveau</label>
        <select id={filterId} className="ns-select" value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="ALL">Tous les niveaux</option>
          <option value="CRITIQUE">Critique</option>
          <option value="MODERE">Modéré</option>
          <option value="NORMAL">Retour à la normale</option>
        </select>
      </div>

      <div className="ns-section" aria-live="polite">
        {visible.length === 0 ? (
          <div className="ns-card ns-empty">
            <strong>Aucune alerte pour le moment</strong>
            {filter === 'ALL'
              ? 'Le journal se remplira dès qu’un département changera de niveau de risque.'
              : 'Aucune alerte de ce niveau. Choisissez « Tous les niveaux » pour voir le journal complet.'}
          </div>
        ) : (
          <ul className="ns-log">
            {visible.map((alert) => (
              <li key={alert.id}>
                <LevelBadge level={alert.level} />
                <span className="ns-log-text">
                  <strong>{alert.department}</strong> passe de « {LEVELS[alert.from].label} » à « {LEVELS[alert.level].label} »
                  {' '}({percent(alert.value)}). {LEVELS[alert.level].recommendation}.
                </span>
                <span className="ns-log-time">{clock(alert.at)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

/* ── Onglet 4 : rapport ── */
function ReportTab({ departments, updatedAt }) {
  const rows = departments.map((dept) => {
    const value = riskScore(dept.metrics);
    return {
      ...dept,
      value,
      level: riskLevel(value),
      incidentCount: dept.incidents.length,
      minutes: dept.incidents.reduce((sum, i) => sum + i.duration_min, 0),
      cost: dept.incidents.reduce((sum, i) => sum + i.cost_eur, 0),
    };
  });
  const totals = rows.reduce(
    (acc, row) => ({ incidents: acc.incidents + row.incidentCount, minutes: acc.minutes + row.minutes, cost: acc.cost + row.cost }),
    { incidents: 0, minutes: 0, cost: 0 },
  );
  const exposed = rows.filter((row) => row.level !== 'NORMAL');

  return (
    <>
      <h2 className="ns-title">Rapport au Ministre</h2>
      <p className="ns-lede">
        Synthèse établie le {updatedAt.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })} à {clock(updatedAt)}.
      </p>

      <div className="ns-toolbar">
        <button type="button" className="ns-button primary" onClick={() => window.print()}>Imprimer le rapport</button>
      </div>

      <div className="ns-section ns-banner" role="note">
        <LevelIcon level="MODERE" />
        <span>
          Prototype : les mesures sont simulées à partir de données synthétiques ({sample.source}) et le score est une
          pondération fixe, pas un modèle entraîné. Les chiffres ci-dessous illustrent le fonctionnement de l’outil.
        </span>
      </div>

      <div className="ns-section ns-grid cols-3">
        <div className="ns-card">
          <p className="ns-tile-label">Incidents recensés en 2025</p>
          <p className="ns-tile-value">{totals.incidents}</p>
          <p className="ns-tile-sub">{number(totals.minutes / 60, 1)} heures d’interruption cumulées</p>
        </div>
        <div className="ns-card">
          <p className="ns-tile-label">Coût estimé de ces incidents</p>
          <p className="ns-tile-value">{euros(totals.cost)}</p>
          <p className="ns-tile-sub">d’après le jeu de données de référence</p>
        </div>
        <div className="ns-card">
          <p className="ns-tile-label">Départements à surveiller</p>
          <p className="ns-tile-value">{exposed.length}</p>
          <p className="ns-tile-sub">{exposed.length ? exposed.map((r) => r.name.replace('Département ', '')).join(', ') : 'aucun à cet instant'}</p>
        </div>
      </div>

      <section className="ns-section ns-card">
        <h3 className="ns-h2">Situation par département</h3>
        <div className="ns-table-wrap">
          <table className="ns-table">
            <thead>
              <tr>
                <th scope="col">Département</th>
                <th scope="col">Niveau</th>
                <th scope="col" className="num">Risque H+1</th>
                <th scope="col" className="num">Incidents 2025</th>
                <th scope="col" className="num">Interruption</th>
                <th scope="col" className="num">Coût estimé</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <th scope="row">{row.name}</th>
                  <td><LevelBadge level={row.level} /></td>
                  <td className="num">{percent(row.value)}</td>
                  <td className="num">{row.incidentCount}</td>
                  <td className="num">{number(row.minutes)} min</td>
                  <td className="num">{euros(row.cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="ns-section ns-grid cols-2">
        <section className="ns-card">
          <h3 className="ns-h2">Actions recommandées</h3>
          <ul className="ns-list">
            {exposed.length === 0 ? <li>Aucune action requise : tous les départements sont stables.</li> : null}
            {exposed.map((row) => (
              <li key={row.id}><strong>{row.name}</strong> — {LEVELS[row.level].recommendation.toLowerCase()}.</li>
            ))}
          </ul>
        </section>
        <section className="ns-card">
          <h3 className="ns-h2">Feuille de route</h3>
          <ul className="ns-list">
            <li>Prototype avec données open source — réalisé.</li>
            <li>Intégration des données réelles du Ministère.</li>
            <li>Ré-entraînement du modèle sur l’historique des incidents.</li>
            <li>Déploiement de l’API en production.</li>
            <li>Tableau de bord Grafana pour les équipes de la DSI.</li>
          </ul>
        </section>
      </div>
    </>
  );
}

/* ── Garde-fou : une erreur d'affichage ne laisse pas une page blanche ── */
class Boundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="ns-main">
        <div className="ns-banner error" role="alert">
          <LevelIcon level="CRITIQUE" />
          <span>
            L’affichage a rencontré une erreur.{' '}
            <button type="button" className="ns-button" onClick={() => window.location.reload()}>Recharger la page</button>
          </span>
        </div>
      </div>
    );
  }
}

export default function NetSentinel() {
  const network = useNetwork();
  const [tab, setTab] = useState('dashboard');
  const [selected, setSelected] = useState(sample.departments[0].id);
  const tabRefs = useRef({});

  const criticalCount = useMemo(
    () => (network ? network.departments.filter((d) => riskLevel(riskScore(d.metrics)) === 'CRITIQUE').length : 0),
    [network],
  );

  // Navigation au clavier entre onglets (flèches, Début, Fin), comme l'attend un lecteur d'écran.
  function onTabKey(event) {
    const index = TABS.findIndex((t) => t.id === tab);
    const moves = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: TABS.length - 1 };
    if (!(event.key in moves)) return;
    event.preventDefault();
    const next = TABS[(moves[event.key] + TABS.length) % TABS.length];
    setTab(next.id);
    tabRefs.current[next.id]?.focus();
  }

  return (
    <div className="ns-app">
      <header className="ns-chrome">
        <div className="ns-chrome-inner">
          <div className="ns-brand">
            <div>
              <h1>NetSentinel</h1>
              <p>Prédiction de coupures réseau — Ministère du Budget</p>
            </div>
            <span className="ns-live" aria-live="off">
              <span className="ns-live-dot" aria-hidden="true" />
              {network ? `Mis à jour à ${clock(network.updatedAt)}` : 'Connexion…'}
            </span>
          </div>
          <div className="ns-tabs" role="tablist" aria-label="Sections du tableau de bord" onKeyDown={onTabKey}>
            {TABS.map((item) => (
              <button
                key={item.id}
                ref={(node) => { tabRefs.current[item.id] = node; }}
                type="button"
                role="tab"
                id={`tab-${item.id}`}
                aria-selected={tab === item.id}
                aria-controls={`panel-${item.id}`}
                tabIndex={tab === item.id ? 0 : -1}
                className="ns-tab"
                onClick={() => setTab(item.id)}
              >
                {item.label}
                {item.id === 'alerts' && criticalCount > 0 ? (
                  <span className="ns-count">
                    {criticalCount}
                    <span className="sr-only"> département(s) en alerte critique</span>
                  </span>
                ) : null}
              </button>
            ))}
          </div>
        </div>
      </header>

      <Boundary>
        <main className="ns-main">
          {/* `key` : le panneau est recréé à chaque changement d'onglet, ce qui rejoue son entrée. */}
          <div key={tab} className="ns-panel" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            {!network ? (
              <div className="ns-grid cards" aria-busy="true" aria-label="Chargement des mesures">
                {[0, 1, 2].map((i) => <div key={i} className="ns-skeleton" />)}
              </div>
            ) : tab === 'dashboard' ? (
              <DashboardTab
                departments={network.departments}
                onOpen={(id) => { setSelected(id); setTab('prediction'); }}
              />
            ) : tab === 'prediction' ? (
              <PredictionTab departments={network.departments} selected={selected} onSelect={setSelected} />
            ) : tab === 'alerts' ? (
              <AlertsTab alerts={network.alerts} />
            ) : (
              <ReportTab departments={network.departments} updatedAt={network.updatedAt} />
            )}
          </div>
        </main>
      </Boundary>
    </div>
  );
}
