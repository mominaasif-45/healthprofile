import type { Clusters } from "@/lib/ml";
import { BarChart, Disclaimer, f3, pct, Scatter } from "./Charts";

export function ClustersTab({ data }: { data: Clusters }) {
  const [v1, v2] = data.pca.explained_variance;
  return (
    <div>
      <Disclaimer>
        <strong>Exploratory analysis. Synthetic data only. Educational demo: not medical advice, not a diagnosis.</strong>{" "}
        Report <code>{data.version}</code>. The clusters are not kinds of people and are not used for any decision or
        prediction.
      </Disclaimer>

      <section className="card" aria-labelledby="clu-what" style={{ marginBottom: 16 }}>
        <h2 id="clu-what">Exploratory clusters of booking behaviour</h2>
        <p className="muted">
          {data.features.length} engagement features: {data.features.join(", ")}. Fitted on the training rows only (seed{" "}
          {data.settings.seed}). The rule for choosing k was fixed before the results were seen: the highest average
          silhouette for k = {data.settings.k_range[0]} to {data.settings.k_range[1]}.
        </p>
      </section>

      <section className="card" aria-labelledby="clu-elbow" style={{ marginBottom: 16 }}>
        <h2 id="clu-elbow">Elbow and silhouette</h2>
        <div className="table-wrap">
          <table>
            <caption className="sr-only">Elbow and silhouette for each k</caption>
            <thead>
              <tr><th scope="col">k</th><th scope="col">Inertia (elbow)</th><th scope="col">Average silhouette</th></tr>
            </thead>
            <tbody>
              {data.elbow.map((row) => (
                <tr key={row.k}>
                  <th scope="row">{row.k}{row.k === data.chosen_k ? " (chosen)" : ""}</th>
                  <td>{Math.round(row.inertia)}</td><td>{f3(row.silhouette)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <BarChart title="Average silhouette for each k (from -1 to 1; higher means better separated)"
                  rows={data.elbow.map((r) => ({ label: `k = ${r.k}`, value: r.silhouette, text: f3(r.silhouette) }))} />
        <p>
          <strong>Chosen: k = {data.chosen_k}.</strong> {data.structure_note}
        </p>
      </section>

      <section className="card" aria-labelledby="clu-pca" style={{ marginBottom: 16 }}>
        <h2 id="clu-pca">2D PCA view</h2>
        <p className="muted">
          {data.pca.points.length} seeded sample points. The two directions keep {pct(v1)} and {pct(v2)} of the spread (
          {pct(v1 + v2)} together), so the picture shows only part of the data: groups that overlap here may be apart in
          the full data, and the reverse.
        </p>
        <Scatter title={`2D PCA view of ${data.pca.points.length} sample points, shaped by K-Means cluster`}
                 points={data.pca.points} />
      </section>

      <section className="card" aria-labelledby="clu-compare" style={{ marginBottom: 16 }}>
        <h2 id="clu-compare">K-Means compared with Agglomerative</h2>
        <div className="table-wrap">
          <table>
            <caption className="sr-only">K-Means and Agglomerative at the chosen k</caption>
            <thead>
              <tr><th scope="col">Method</th><th scope="col">Average silhouette</th><th scope="col">Cluster sizes</th></tr>
            </thead>
            <tbody>
              <tr><th scope="row">K-Means</th><td>{f3(data.kmeans.silhouette)}</td><td>{data.kmeans.sizes.join(" / ")}</td></tr>
              <tr>
                <th scope="row">Agglomerative ({data.agglomerative.linkage})</th>
                <td>{f3(data.agglomerative.silhouette)}</td><td>{data.agglomerative.sizes.join(" / ")}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p>
          Agreement between the two methods (adjusted Rand index, 1 = identical, 0 = no better than chance):{" "}
          <strong>{f3(data.agglomerative.adjusted_rand_vs_kmeans)}</strong>. Stability: the {data.validation.rows}{" "}
          validation rows, assigned without refitting, have an average silhouette of {f3(data.validation.silhouette)}.
        </p>
      </section>

      <section className="card" aria-labelledby="clu-summary" style={{ marginBottom: 16 }}>
        <h2 id="clu-summary">What each cluster looks like</h2>
        <ul>
          {data.summary.map((c) => (
            <li key={c.cluster}>
              <strong>Cluster {c.cluster}</strong> ({c.rows} rows, {pct(c.share)}): {c.description}
            </li>
          ))}
        </ul>
        <p className="muted">
          These describe booking behaviour in synthetic rows. K-Means always finds k groups, even with no real groups;
          different features, scaling or seeds would give different groups.
        </p>
      </section>
    </div>
  );
}
