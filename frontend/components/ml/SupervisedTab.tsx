import type { Workbench } from "@/lib/ml";
import { BarChart, Disclaimer, f3, pct, signed } from "./Charts";

export const MODEL_NAMES: Record<string, string> = {
  baseline: "Baseline",
  logistic_regression: "Logistic regression",
  random_forest: "Random forest",
  gradient_boosting: "Gradient boosting",
};
const ORDER = ["baseline", "logistic_regression", "random_forest", "gradient_boosting"];
const LIVE = "logistic_regression"; // noshow-1.0.0, chosen in Week 3 on the validation pile
const name = (key: string) => MODEL_NAMES[key] ?? key;

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section className="card" aria-labelledby={id} style={{ marginBottom: 16 }}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}

export function SupervisedTab({ data }: { data: Workbench }) {
  const keys = ORDER.filter((k) => data.models[k]);
  const live = data.models[LIVE].validation;
  const best = data.best_on_validation;
  const sorted = [...keys].sort((a, b) => data.models[b].validation.pr_auc - data.models[a].validation.pr_auc);
  const runnerUp = sorted.find((k) => k !== best)!;
  const tieGap = data.models[best].validation.pr_auc - data.models[runnerUp].validation.pr_auc;
  const piles = data.pile_sizes;

  return (
    <div>
      <Disclaimer>
        <strong>Synthetic data only. Educational demo: not medical advice, not a diagnosis</strong>, and not a prediction
        about any real person. Report <code>{data.version}</code> (scikit-learn {data.settings.scikit_learn}); the live
        no-show demo still uses <code>{data.settings.shipped_model}</code> (logistic regression).
      </Disclaimer>

      <p className="muted">
        Data: split seed {data.settings.split_seed}, model seed {data.settings.model_seed}, {data.settings.cv_folds}-fold
        stratified cross-validation; {piles.train.rows} training, {piles.validation.rows} validation and{" "}
        {piles.test.rows} test rows. Every choice below uses the validation pile only.
      </p>

      <Section id="sup-compare" title="Validation comparison">
        <div className="table-wrap">
          <table>
            <caption className="sr-only">Validation comparison of the four models</caption>
            <thead>
              <tr>
                <th scope="col">Model</th><th scope="col">ROC-AUC</th><th scope="col">PR-AUC</th>
                <th scope="col">Threshold</th><th scope="col">Precision</th><th scope="col">Recall</th>
                <th scope="col">F1</th><th scope="col">CV PR-AUC (mean ± sd)</th><th scope="col">CV ROC-AUC (mean ± sd)</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => {
                const m = data.models[k];
                return (
                  <tr key={k}>
                    <th scope="row">{name(k)}</th>
                    <td>{f3(m.validation.roc_auc)}</td><td>{f3(m.validation.pr_auc)}</td>
                    <td>{m.validation.threshold.toFixed(2)}</td><td>{f3(m.validation.precision)}</td>
                    <td>{f3(m.validation.recall)}</td><td>{f3(m.validation.f1)}</td>
                    <td>{f3(m.cv.pr_auc.mean)} ± {f3(m.cv.pr_auc.sd)}</td>
                    <td>{f3(m.cv.roc_auc.mean)} ± {f3(m.cv.roc_auc.sd)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <BarChart title="Validation PR-AUC by model (higher is better)"
                  rows={keys.map((k) => ({ label: name(k), value: data.models[k].validation.pr_auc,
                                           text: f3(data.models[k].validation.pr_auc) }))} />
      </Section>

      <Section id="sup-choice" title="Which model and why">
        <p>
          The live demo uses <strong>Logistic regression</strong> (<code>{data.settings.shipped_model}</code>), chosen in
          Week 3 on the <strong>validation pile only</strong>, with its decision line at{" "}
          <strong>{live.threshold.toFixed(2)}</strong> (the best F1 on validation).
        </p>
        <p>
          In this comparison the highest validation PR-AUC belongs to <strong>{name(best)}</strong> (
          {f3(data.models[best].validation.pr_auc)}), only {f3(tieGap)} above {name(runnerUp)}: a difference that small
          can be luck on {piles.validation.rows} rows, so it is a label for the inspection below, not a reason to replace
          the live model.
        </p>
      </Section>

      <Section id="sup-matrix" title="Confusion matrix at the decision line">
        <div className="table-wrap">
          <table>
            <caption>
              Confusion matrix: logistic regression, validation pile, decision line {live.threshold.toFixed(2)}
            </caption>
            <thead>
              <tr>
                <th scope="col">Actual outcome</th>
                <th scope="col">Flagged (estimate ≥ {live.threshold.toFixed(2)})</th>
                <th scope="col">Not flagged (below {live.threshold.toFixed(2)})</th>
              </tr>
            </thead>
            <tbody>
              <tr><th scope="row">Missed the appointment</th><td>{live.tp} caught</td><td>{live.fn} missed</td></tr>
              <tr><th scope="row">Attended</th><td>{live.fp} false alarms</td><td>{live.tn} correctly cleared</td></tr>
            </tbody>
          </table>
        </div>
        <p className="muted">
          Precision {pct(live.precision)}: of the flagged appointments, this share were real no-shows. Recall{" "}
          {pct(live.recall)}: of the real no-shows, this share were flagged. A flag suggests an extra reminder, not a
          certain no-show.
        </p>
      </Section>

      <Section id="sup-importance" title="Permutation importance">
        <p className="muted">
          How much validation PR-AUC drops when one input is shuffled (logistic regression, the live model). Near zero or
          below means the model barely relies on it; small negative values are noise.
        </p>
        <BarChart title="Drop in PR-AUC when each input is shuffled"
                  rows={data.importance[LIVE].map((r) => ({ label: r.feature, value: r.mean,
                                                            text: `${signed(r.mean)} ± ${r.sd.toFixed(3)}` }))} />
      </Section>

      <Section id="sup-gap" title="Training versus validation (overfitting)">
        <div className="table-wrap">
          <table>
            <caption className="sr-only">Training versus validation PR-AUC</caption>
            <thead>
              <tr>
                <th scope="col">Model</th><th scope="col">Train PR-AUC</th><th scope="col">Validation PR-AUC</th>
                <th scope="col">Gap</th><th scope="col">Gap above {data.settings.overfit_gap.toFixed(2)}?</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => {
                const m = data.models[k];
                return (
                  <tr key={k}>
                    <th scope="row">{name(k)}</th><td>{f3(m.train.pr_auc)}</td><td>{f3(m.validation.pr_auc)}</td>
                    <td>{signed(m.gap.pr_auc)}</td><td>{m.gap.overfit ? "yes" : "no"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>

      <Section id="sup-errors" title="False positives and false negatives">
        <p className="muted">
          {name(data.errors.model)} on the validation pile at its line {data.errors.threshold.toFixed(2)}: what each kind
          of mistake looks like on average.
        </p>
        <div className="table-wrap">
          <table>
            <caption className="sr-only">Average profile of each kind of right and wrong flag</caption>
            <thead>
              <tr>
                <th scope="col">Box</th><th scope="col">Rows</th><th scope="col">Average estimate</th>
                <th scope="col">No reminder</th><th scope="col">Average lead days</th>
                <th scope="col">Any earlier missed visit</th><th scope="col">Booked by phone</th>
              </tr>
            </thead>
            <tbody>
              {data.errors.profile.map((p) => (
                <tr key={p.box}>
                  <th scope="row">{p.box}</th><td>{p.rows}</td><td>{f3(p.mean_predicted)}</td>
                  <td>{pct(p.no_reminder)}</td><td>{p.mean_lead_time.toFixed(1)}</td>
                  <td>{pct(p.any_prior_no_show)}</td><td>{pct(p.phone_booking)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {([["Most confident false alarms (flagged, but attended)", data.errors.false_alarms],
           ["Most confident missed no-shows (not flagged, but missed)", data.errors.misses]] as const).map(([label, rows]) => (
          <div key={label}>
            <h3 style={{ fontSize: 15, marginTop: 12 }}>{label}</h3>
            <ul>
              {rows.slice(0, 5).map((r) => (
                <li key={r.appointment_id}>
                  {r.appointment_id}: estimate {f3(r.p)}, booked {r.lead_time_days} days ahead, reminder{" "}
                  {r.reminder_sent ?? "not recorded"}, {r.booking_channel}
                </li>
              ))}
            </ul>
          </div>
        ))}
        <p className="muted">The data is noisy on purpose, so some confident mistakes are chance, not the model.</p>
      </Section>

      <Section id="sup-test" title="Test pile (used once, after the choice)">
        <p>
          Reported once, after every choice above was made on validation, and <strong>not used to choose</strong>{" "}
          anything. Thresholds are the ones frozen on validation. Note: these {piles.test.rows} rows were already used once
          in Week 3 to report the Week 3 models.
        </p>
        <div className="table-wrap">
          <table>
            <caption className="sr-only">Test pile results</caption>
            <thead>
              <tr>
                <th scope="col">Model</th><th scope="col">ROC-AUC</th><th scope="col">PR-AUC</th>
                <th scope="col">Threshold</th><th scope="col">Precision</th><th scope="col">Recall</th>
              </tr>
            </thead>
            <tbody>
              {keys.filter((k) => data.test[k]).map((k) => {
                const t = data.test[k];
                return (
                  <tr key={k}>
                    <th scope="row">{name(k)}</th><td>{f3(t.roc_auc)}</td><td>{f3(t.pr_auc)}</td>
                    <td>{t.threshold.toFixed(2)}</td><td>{f3(t.precision)}</td><td>{f3(t.recall)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}
