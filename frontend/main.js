// URL del backend (porta 5000 su Codespaces)
const API_BASE = "https://ominous-space-sniffle-jjrp9jr549952q4x6-5000.app.github.dev/api";

// --- AUTENTICAZIONE / RUOLI ---
let authToken = null;
let currentUser = null;

function loadAuthFromStorage() {
  try {
    const token = localStorage.getItem("token");
    const userStr = localStorage.getItem("user");
    if (token && userStr) {
      authToken = token;
      currentUser = JSON.parse(userStr);
    }
  } catch (e) {
    console.error("Errore nel parsing user da localStorage", e);
  }
}

function saveAuthToStorage(token, user) {
  authToken = token;
  currentUser = user;
  localStorage.setItem("token", token);
  localStorage.setItem("user", JSON.stringify(user));
}

function clearAuth() {
  authToken = null;
  currentUser = null;
  localStorage.removeItem("token");
  localStorage.removeItem("user");
}

// aggiunge automaticamente Authorization se loggato
function getAuthHeaders(extra = {}) {
  const headers = { ...extra };
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }
  return headers;
}

// mostra/nasconde pezzi di UI in base al ruolo
function updateAuthUI() {
  const infoEl = document.getElementById("auth-user-info");
  const logoutBtn = document.getElementById("logout-btn");
  const addTorrentCard = document.getElementById("add-torrent-card");
  const commentForm = document.getElementById("comment-form");

  const isLogged = !!currentUser;

  if (infoEl) {
    if (isLogged) {
      infoEl.textContent = `Loggato come ${currentUser.username} (ruolo: ${currentUser.role})`;
    } else {
      infoEl.textContent = "Non sei loggato (guest)";
    }
  }

  if (logoutBtn) {
    logoutBtn.style.display = isLogged ? "inline-block" : "none";
  }

  // guest non può aggiungere torrent
  if (addTorrentCard) {
    addTorrentCard.style.display = isLogged ? "block" : "none";
  }

  // guest non può aggiungere commenti: disabilitiamo il form
  if (commentForm) {
    const controls = commentForm.querySelectorAll("input,select,button");
    controls.forEach(el => {
      el.disabled = !isLogged;
    });
  }
}

// --- LOGIN / REGISTER / LOGOUT ---

async function handleLogin() {
  const username = document.getElementById("auth-username").value.trim();
  const password = document.getElementById("auth-password").value;

  if (!username || !password) {
    alert("Inserisci username e password per il login.");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });

    const data = await res.json();

    if (!res.ok) {
      alert(data.error || "Errore di login");
      return;
    }

    saveAuthToStorage(data.token, data.user);
    updateAuthUI();
    alert("Login effettuato!");
  } catch (err) {
    console.error(err);
    alert("Errore di rete durante il login");
  }
}

async function handleRegister() {
  const username = document.getElementById("auth-username").value.trim();
  const email = document.getElementById("auth-email").value.trim();
  const password = document.getElementById("auth-password").value;

  if (!username || !email || !password) {
    alert("Compila username, email e password per la registrazione.");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, email, password })
    });

    const data = await res.json();

    if (!res.ok) {
      if (data.errors) {
        alert(data.errors.join("\n"));
      } else {
        alert(data.error || "Errore di registrazione");
      }
      return;
    }

    saveAuthToStorage(data.token, data.user);
    updateAuthUI();
    alert("Registrazione completata e login effettuato!");
  } catch (err) {
    console.error(err);
    alert("Errore di rete durante la registrazione");
  }
}

function handleLogout() {
  clearAuth();
  updateAuthUI();
  alert("Logout effettuato.");
}

// --- STATO TORRENT DETTAGLIO ---

let currentTorrentId = null;
let torrentModal = null;

// ---- LISTA + FILTRI TORRENTS ----

async function fetchTorrents(filters = {}) {
  const params = new URLSearchParams();

  if (filters.title) params.append("title", filters.title);
  if (filters.description) params.append("description", filters.description);
  if (filters.categories) params.append("categories", filters.categories);
  if (filters.fromDate) params.append("fromDate", filters.fromDate);
  if (filters.toDate) params.append("toDate", filters.toDate);
  if (filters.minSize) params.append("minSize", filters.minSize);
  if (filters.maxSize) params.append("maxSize", filters.maxSize);
  if (filters.sort) params.append("sort", filters.sort);
  if (filters.order) params.append("order", filters.order);

  let url = `${API_BASE}/torrents`;
  const qs = params.toString();
  if (qs) {
    url += `?${qs}`;
  }

  console.log("Chiamata API:", url);

  const res = await fetch(url);
  const data = await res.json();
  renderTorrents(data);
}

function renderTorrents(torrents) {
  const container = document.getElementById("torrents-container");
  container.innerHTML = "";

  if (!torrents.length) {
    container.innerHTML = `
      <div class="col-12">
        <div class="alert alert-warning mb-0">Nessun torrent trovato.</div>
      </div>
    `;
    return;
  }

  torrents.forEach(t => {
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
            <button class="btn btn-sm btn-primary" onclick="showDetails('${t._id}')">
              Dettagli
            </button>
          </div>
        </div>
      </div>
    `;
    container.appendChild(col);
  });
}

// ---- AGGIUNTA TORRENT (solo user+) ----

async function handleAddTorrent(e) {
  e.preventDefault();

  const title = document.getElementById("torrent-title").value.trim();
  const description = document.getElementById("torrent-description").value.trim();
  const size = document.getElementById("torrent-size").value;
  const categories = document.getElementById("torrent-categories").value.trim();
  const file_url = document.getElementById("torrent-file-url").value.trim();
  const images = document.getElementById("torrent-images").value.trim();

  if (!title || !description || !file_url) {
    alert("Titolo, descrizione e URL del file .torrent sono obbligatori.");
    return;
  }

  const payload = {
    title,
    description,
    size: size !== "" ? Number(size) : null,
    categories, // il backend accetta stringa "a,b,c" oppure array
    file_url,
    images
  };

  try {
    const res = await fetch(`${API_BASE}/torrents`, {
      method: "POST",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      console.error("Errore API create_torrent:", err);
      alert(
        "Errore nel salvataggio del torrent: " +
          (err.errors ? err.errors.join(", ") : err.error || "richiesta non valida")
      );
      return;
    }

    // pulisco il form
    document.getElementById("add-torrent-form").reset();

    // ricarico la lista torrent (senza filtri)
    fetchTorrents();
  } catch (error) {
    console.error(error);
    alert("Errore di rete nel salvataggio del torrent");
  }
}

// ---- DETTAGLIO + COMMENTI ----

async function showDetails(id) {
  currentTorrentId = id;

  try {
    const [torrentRes, commentsRes] = await Promise.all([
      fetch(`${API_BASE}/torrents/${id}`),
      fetch(`${API_BASE}/torrents/${id}/comments`)
    ]);

    const torrent = await torrentRes.json();
    const comments = await commentsRes.json();

    renderTorrentDetails(torrent);
    renderComments(comments);

    if (torrentModal) {
      torrentModal.show();
    }
  } catch (err) {
    console.error(err);
    alert("Errore nel caricamento del dettaglio torrent");
  }
}

function renderTorrentDetails(t) {
  const div = document.getElementById("torrent-details");
  const categories = (t.categories || []).join(", ");
  const avgRating = t.average_rating != null ? Number(t.average_rating).toFixed(2) : "N/A";
  const ratingsCount = t.ratings_count || 0;

  div.innerHTML = `
    <h5>${t.title}</h5>
    <p>${t.description || ""}</p>
    <p class="mb-1">
      <strong>Dimensione:</strong> ${t.size || "?"} MB<br>
      <strong>Categorie:</strong> ${categories || "N/A"}
    </p>
    <p class="mb-0">
      <strong>Valutazione media:</strong> ${avgRating} (${ratingsCount} voti)
    </p>
  `;
}

function renderComments(comments) {
  const list = document.getElementById("comments-list");
  list.innerHTML = "";

  if (!comments.length) {
    list.innerHTML = `<p class="text-muted">Non ci sono ancora commenti.</p>`;
    return;
  }

  comments.forEach(c => {
    const div = document.createElement("div");
    div.className = "border rounded p-2 mb-2";

    const author = c.author_name || "Anonimo";
    const createdAt = c.created_at ? new Date(c.created_at).toLocaleString() : "";
    const ratingStars = "⭐".repeat(c.rating || 0);

    div.innerHTML = `
      <div class="d-flex justify-content-between align-items-center">
        <div>
          <strong>${author}</strong> - <span class="text-warning">${ratingStars}</span>
        </div>
        <small class="text-muted">${createdAt}</small>
      </div>
      <p class="mb-1">${c.text}</p>
      <div class="text-end">
        <button class="btn btn-sm btn-outline-secondary me-2" onclick="editComment('${c._id}')">Modifica</button>
        <button class="btn btn-sm btn-outline-danger" onclick="deleteComment('${c._id}')">Elimina</button>
      </div>
    `;
    list.appendChild(div);
  });
}

// ---- AGGIUNTA COMMENTO ----

async function handleCommentSubmit(e) {
  e.preventDefault();
  if (!currentTorrentId) return;

  const author = document.getElementById("comment-author").value.trim();
  const rating = document.getElementById("comment-rating").value;
  const text = document.getElementById("comment-text").value.trim();

  if (!text) {
    alert("Il commento non può essere vuoto");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/torrents/${currentTorrentId}/comments`, {
      method: "POST",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        author_name: author || (currentUser ? currentUser.username : "Anonimo"),
        rating,
        text
      })
    });

    if (!res.ok) {
      const err = await res.json();
      alert("Errore: " + (err.error || "impossibile aggiungere il commento"));
      return;
    }

    document.getElementById("comment-text").value = "";

    // ricarico commenti e dettagli per aggiornare media
    const [commentsRes, torrentRes] = await Promise.all([
      fetch(`${API_BASE}/torrents/${currentTorrentId}/comments`),
      fetch(`${API_BASE}/torrents/${currentTorrentId}`)
    ]);

    const comments = await commentsRes.json();
    const torrent = await torrentRes.json();
    renderComments(comments);
    renderTorrentDetails(torrent);
  } catch (err) {
    console.error(err);
    alert("Errore nell'invio del commento");
  }
}

// ---- MODIFICA COMMENTO (semplice con prompt) ----

async function editComment(id) {
  const newText = prompt("Nuovo testo del commento:");
  if (newText === null || !newText.trim()) return;

  const newRatingStr = prompt("Nuovo voto (1-5):");
  if (newRatingStr === null) return;
  const newRating = parseInt(newRatingStr, 10);
  if (isNaN(newRating) || newRating < 1 || newRating > 5) {
    alert("Voto non valido");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/comments/${id}`, {
      method: "PUT",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        text: newText.trim(),
        rating: newRating
      })
    });

    if (!res.ok) {
      const err = await res.json();
      alert("Errore: " + (err.error || "impossibile modificare il commento"));
      return;
    }

    const [commentsRes, torrentRes] = await Promise.all([
      fetch(`${API_BASE}/torrents/${currentTorrentId}/comments`),
      fetch(`${API_BASE}/torrents/${currentTorrentId}`)
    ]);

    const comments = await commentsRes.json();
    const torrent = await torrentRes.json();
    renderComments(comments);
    renderTorrentDetails(torrent);
  } catch (err) {
    console.error(err);
    alert("Errore nella modifica del commento");
  }
}

// ---- ELIMINA COMMENTO (solo moderator+ lato backend) ----

async function deleteComment(id) {
  if (!confirm("Sei sicuro di voler eliminare questo commento?")) return;

  try {
    const res = await fetch(`${API_BASE}/comments/${id}`, {
      method: "DELETE",
      headers: getAuthHeaders()
    });

    if (!res.ok) {
      const err = await res.json();
      alert("Errore: " + (err.error || "impossibile eliminare il commento"));
      return;
    }

    const [commentsRes, torrentRes] = await Promise.all([
      fetch(`${API_BASE}/torrents/${currentTorrentId}/comments`),
      fetch(`${API_BASE}/torrents/${currentTorrentId}`)
    ]);

    const comments = await commentsRes.json();
    const torrent = await torrentRes.json();
    renderComments(comments);
    renderTorrentDetails(torrent);
  } catch (err) {
    console.error(err);
    alert("Errore nell'eliminazione del commento");
  }
}

// ---- INIT DOM ----

document.addEventListener("DOMContentLoaded", () => {
  // carico eventuale login salvato
  loadAuthFromStorage();

  // filtri
  const form = document.getElementById("filters-form");
  const resetBtn = document.getElementById("reset-filters");

  // form aggiunta torrent
  const addTorrentForm = document.getElementById("add-torrent-form");
  if (addTorrentForm) {
    addTorrentForm.addEventListener("submit", handleAddTorrent);
  }

  // auth buttons
  const loginBtn = document.getElementById("login-btn");
  const registerBtn = document.getElementById("register-btn");
  const logoutBtn = document.getElementById("logout-btn");

  if (loginBtn) {
    loginBtn.addEventListener("click", handleLogin);
  }
  if (registerBtn) {
    registerBtn.addEventListener("click", handleRegister);
  }
  if (logoutBtn) {
    logoutBtn.addEventListener("click", handleLogout);
  }

  // prima chiamata: senza filtri
  if (form) {
    fetchTorrents();

    form.addEventListener("submit", (e) => {
      e.preventDefault();

      const filters = {
        title: document.getElementById("title").value.trim(),
        description: document.getElementById("description").value.trim(),
        categories: document.getElementById("categories").value.trim(),
        fromDate: document.getElementById("fromDate").value,
        toDate: document.getElementById("toDate").value,
        minSize: document.getElementById("minSize").value,
        maxSize: document.getElementById("maxSize").value,
        sort: document.getElementById("sort").value,
        order: document.getElementById("order").value
      };

      fetchTorrents(filters);
    });

    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        form.reset();
        fetchTorrents();
      });
    }
  }

  // modale e form commenti
  const modalElement = document.getElementById("torrentModal");
  if (modalElement && window.bootstrap) {
    torrentModal = new bootstrap.Modal(modalElement);
  }

  const commentForm = document.getElementById("comment-form");
  if (commentForm) {
    commentForm.addEventListener("submit", handleCommentSubmit);
  }

  // aggiorna UI in base al ruolo (guest/user/mod)
  updateAuthUI();
});
