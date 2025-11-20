// Sostituisci con l'URL del tuo backend in Codespaces (quello della porta 5000)
// Esempio: const API_BASE = "https://5000-xxxxx-username-…github.dev/api";
const API_BASE = "https://ominous-space-sniffle-jjrp9jr549952q4x6-5000.app.github.dev/api"; // in locale; in Codespaces usa l'URL pubblico

async function fetchTorrents(query = "") {
  let url = `${API_BASE}/torrents`;
  // Per ora ignoro il filtraggio lato API, gestisco solo client-side
  const res = await fetch(url);
  const data = await res.json();
  renderTorrents(data, query);
}

function renderTorrents(torrents, query = "") {
  const container = document.getElementById("torrents-container");
  container.innerHTML = "";

  const normalizedQuery = query.toLowerCase().trim();

  const filtered = torrents.filter(t => {
    if (!normalizedQuery) return true;
    const title = (t.title || "").toLowerCase();
    const description = (t.description || "").toLowerCase();
    return title.includes(normalizedQuery) || description.includes(normalizedQuery);
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="col-12">
        <div class="alert alert-warning">Nessun torrent trovato.</div>
      </div>
    `;
    return;
  }

  filtered.forEach(t => {
    const col = document.createElement("div");
    col.className = "col-md-4";

    const categories = (t.categories || []).join(", ");

    col.innerHTML = `
      <div class="card h-100">
        <div class="card-body d-flex flex-column">
          <h5 class="card-title">${t.title}</h5>
          <p class="card-text small">${t.description || ""}</p>
          <p class="card-text">
            <small class="text-muted">
              Dimensione: ${t.size || "?"} MB<br>
              Categorie: ${categories || "N/A"}
            </small>
          </p>
          <div class="mt-auto">
            <button class="btn btn-sm btn-primary" disabled>Dettagli (WIP)</button>
          </div>
        </div>
      </div>
    `;
    container.appendChild(col);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("search-input");

  // Prima chiamata: carico tutto
  fetchTorrents();

  // Filtra in tempo reale mentre l'utente digita
  searchInput.addEventListener("input", (e) => {
    fetchTorrents(e.target.value);
  });
});
