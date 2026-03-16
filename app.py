import streamlit as st
import groq
import base64
from PIL import Image
import io
import sqlite3
import re
import hashlib
from datetime import date
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Nutrily", layout="wide")

# ── Estilo da tela de login ─────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap');

[data-testid="stAppViewContainer"] {
    background: #0f0f0f;
}

.login-logo {
    font-family: 'DM Serif Display', serif;
    font-size: 2.4rem;
    color: #f5f0e8;
    text-align: center;
    margin-bottom: 0.25rem;
    letter-spacing: -0.5px;
}

.login-sub {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.85rem;
    color: #666;
    text-align: center;
    margin-bottom: 2.5rem;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}

.login-error {
    background: rgba(220, 53, 69, 0.12);
    border: 1px solid rgba(220, 53, 69, 0.3);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    color: #ff6b6b;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.875rem;
    margin-bottom: 1rem;
    text-align: center;
}

.login-success {
    background: rgba(40, 167, 69, 0.12);
    border: 1px solid rgba(40, 167, 69, 0.3);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    color: #51cf66;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.875rem;
    margin-bottom: 1rem;
    text-align: center;
}

.user-badge {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 0.4rem 0.9rem;
    color: #c8a96e;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.82rem;
    display: inline-block;
}
</style>
""", unsafe_allow_html=True)

CHAVE = st.secrets["GROQ_API_KEY"]
client = groq.Groq(api_key=CHAVE)

# ── Banco de dados ──────────────────────────────────────────
def init_db():
    conn = sqlite3.connect("nutri.db")

    # Tabela de usuários
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabela de refeições com user_id
    conn.execute("""
        CREATE TABLE IF NOT EXISTS refeicoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 1,
            data TEXT NOT NULL,
            descricao TEXT,
            calorias REAL,
            proteinas REAL,
            carboidratos REAL,
            gorduras REAL,
            fibras REAL,
            analise_completa TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migrações para DBs antigos
    for col, tipo in [("fibras", "REAL DEFAULT 0.0"), ("user_id", "INTEGER DEFAULT 1")]:
        try:
            conn.execute(f"ALTER TABLE refeicoes ADD COLUMN {col} {tipo}")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()

# ── Auth ────────────────────────────────────────────────────
def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def cadastrar_usuario(username, senha):
    try:
        conn = sqlite3.connect("nutri.db")
        conn.execute(
            "INSERT INTO usuarios (username, password_hash) VALUES (?, ?)",
            (username.strip().lower(), hash_senha(senha))
        )
        conn.commit()
        conn.close()
        return True, "Conta criada com sucesso!"
    except sqlite3.IntegrityError:
        return False, "Nome de usuário já existe."

def autenticar_usuario(username, senha):
    conn = sqlite3.connect("nutri.db")
    row = conn.execute(
        "SELECT id, username FROM usuarios WHERE username = ? AND password_hash = ?",
        (username.strip().lower(), hash_senha(senha))
    ).fetchone()
    conn.close()
    if row:
        return True, {"id": row[0], "username": row[1]}
    return False, None

# ── Refeições ───────────────────────────────────────────────
def salvar_refeicao(user_id, data, descricao, calorias, proteinas, carboidratos, gorduras, fibras, analise):
    conn = sqlite3.connect("nutri.db")
    conn.execute("""
        INSERT INTO refeicoes (user_id, data, descricao, calorias, proteinas, carboidratos, gorduras, fibras, analise_completa)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, data, descricao, calorias, proteinas, carboidratos, gorduras, fibras, analise))
    conn.commit()
    conn.close()

def carregar_refeicoes(user_id, data=None):
    conn = sqlite3.connect("nutri.db")
    if data:
        df = pd.read_sql(
            "SELECT * FROM refeicoes WHERE user_id = ? AND data = ? ORDER BY created_at DESC",
            conn, params=(user_id, data)
        )
    else:
        df = pd.read_sql(
            "SELECT * FROM refeicoes WHERE user_id = ? ORDER BY data DESC, created_at DESC",
            conn, params=(user_id,)
        )
    conn.close()
    return df

def carregar_totais_por_dia(user_id):
    conn = sqlite3.connect("nutri.db")
    df = pd.read_sql("""
        SELECT data,
               SUM(calorias) as calorias,
               SUM(proteinas) as proteinas,
               SUM(carboidratos) as carboidratos,
               SUM(gorduras) as gorduras,
               SUM(fibras) as fibras
        FROM refeicoes
        WHERE user_id = ?
        GROUP BY data
        ORDER BY data ASC
    """, conn, params=(user_id,))
    conn.close()
    return df

def deletar_refeicao(id):
    conn = sqlite3.connect("nutri.db")
    conn.execute("DELETE FROM refeicoes WHERE id = ?", (id,))
    conn.commit()
    conn.close()

def extrair_macros(texto):
    linhas = texto.split("\n")
    idx_total = -1
    for i, linha in enumerate(linhas):
        if "total" in linha.lower():
            idx_total = i
            break
    if idx_total == -1:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    for linha in linhas[idx_total:idx_total + 4]:
        linha_limpa = linha.replace("*", "").replace(",", ".")
        numeros = re.findall(r"\b(\d+\.?\d*)\b", linha_limpa)
        numeros = [float(n) for n in numeros if float(n) > 0]
        if len(numeros) >= 5:
            return numeros[0], numeros[1], numeros[2], numeros[3], numeros[4]
        elif len(numeros) == 4:
            return numeros[0], numeros[1], numeros[2], numeros[3], 0.0
        elif len(numeros) == 3:
            return numeros[0], numeros[1], numeros[2], 0.0, 0.0
    return 0.0, 0.0, 0.0, 0.0, 0.0

init_db()

# ── Session state ───────────────────────────────────────────
if "usuario" not in st.session_state:
    st.session_state.usuario = None

# ── Tela de Login / Cadastro ────────────────────────────────
if st.session_state.usuario is None:

    _, col_center, _ = st.columns([1, 1.2, 1])

    with col_center:
        st.markdown('<div class="login-logo">🥗 Nutrily</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-sub">Macro Tracker</div>', unsafe_allow_html=True)

        modo = st.radio("", ["Entrar", "Criar conta"], horizontal=True, label_visibility="collapsed")
        st.markdown("---")

        username = st.text_input("Usuário", placeholder="seu_usuario")
        senha = st.text_input("Senha", type="password", placeholder="••••••••")

        if modo == "Entrar":
            if st.button("Entrar →", use_container_width=True):
                if username and senha:
                    ok, user = autenticar_usuario(username, senha)
                    if ok:
                        st.session_state.usuario = user
                        st.rerun()
                    else:
                        st.markdown('<div class="login-error">❌ Usuário ou senha incorretos.</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="login-error">Preencha todos os campos.</div>', unsafe_allow_html=True)
        else:
            if st.button("Criar conta →", use_container_width=True):
                if username and senha:
                    if len(senha) < 4:
                        st.markdown('<div class="login-error">A senha deve ter pelo menos 4 caracteres.</div>', unsafe_allow_html=True)
                    else:
                        ok, msg = cadastrar_usuario(username, senha)
                        if ok:
                            st.markdown(f'<div class="login-success">✅ {msg} Faça login.</div>', unsafe_allow_html=True)
                        else:
                            st.markdown(f'<div class="login-error">❌ {msg}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="login-error">Preencha todos os campos.</div>', unsafe_allow_html=True)

    st.stop()

# ── App principal (usuário logado) ──────────────────────────
user = st.session_state.usuario

col_title, col_logout = st.columns([5, 1])
with col_title:
    st.title("🥗 Nutrily — Macro Tracker")
with col_logout:
    st.markdown(f'<div class="user-badge">👤 {user["username"]}</div>', unsafe_allow_html=True)
    if st.button("Sair"):
        st.session_state.usuario = None
        st.rerun()

aba1, aba2, aba3 = st.tabs(["📸 Analisar Refeição", "📅 Diário Alimentar", "📊 Gráficos de Progresso"])

# ── ABA 1: Analisar ─────────────────────────────────────────
with aba1:
    col1, col2 = st.columns([1, 1])

    with col1:
        uploaded_file = st.file_uploader("Suba a foto do prato", type=["jpg", "png", "jpeg"])
        data_refeicao = st.date_input("Data da refeição", value=date.today(), format="DD/MM/YYYY")
        opcao_descricao = st.selectbox(
            "Refeição",
            ["☕ Café da manhã", "🥗 Almoço", "🍎 Lanche da tarde", "🍽️ Jantar", "🌙 Ceia", "✏️ Outro..."]
        )
        if opcao_descricao == "✏️ Outro...":
            descricao = st.text_input("Descreva a refeição", placeholder="Ex: Pré-treino, Cheat meal...")
        else:
            descricao = opcao_descricao

        info_prato = st.text_input(
            "🍽️ Descreva o prato (opcional, melhora a precisão)",
            placeholder="Ex: Costelinha de porco com molho de limão..."
        )

        if uploaded_file:
            img = Image.open(uploaded_file)
            st.image(img, use_container_width=True)

    with col2:
        if uploaded_file and st.button("🔍 Calcular Macros", use_container_width=True):
            try:
                img_bytes = io.BytesIO()
                img.save(img_bytes, format="JPEG")
                img_bytes.seek(0)
                img_base64 = base64.b64encode(img_bytes.read()).decode("utf-8")

                contexto = f" — o prato é: {info_prato}" if info_prato else ""

                prompt = f"""Atue como nutricionista. Analise a imagem{contexto} e responda APENAS com uma tabela Markdown no formato abaixo, sem texto adicional antes ou depois:

| Alimento | Quantidade | Calorias (kcal) | Proteínas (g) | Carboidratos (g) | Gorduras (g) | Fibras (g) |
|----------|------------|-----------------|---------------|------------------|--------------|------------|
| [alimento] | [qtd] | [cal] | [prot] | [carb] | [gord] | [fibras] |
| **TOTAL** | | [total_cal] | [total_prot] | [total_carb] | [total_gord] | [total_fibras] |

Use apenas números nas células de valores, sem unidades dentro da tabela."""

                with st.spinner("Analisando imagem..."):
                    response = client.chat.completions.create(
                        model="meta-llama/llama-4-scout-17b-16e-instruct",
                        temperature=0,
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}},
                                {"type": "text", "text": prompt}
                            ]
                        }],
                        max_tokens=1024,
                    )

                analise = response.choices[0].message.content
                calorias, proteinas, carboidratos, gorduras, fibras = extrair_macros(analise)

                st.success("✅ Análise concluída!")
                if info_prato:
                    st.info(f"🍽️ Análise baseada em: **{info_prato}**")
                st.markdown(analise)
                st.divider()

                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("🔥 Calorias", f"{calorias:.0f} kcal")
                c2.metric("💪 Proteínas", f"{proteinas:.1f}g")
                c3.metric("🍞 Carboidratos", f"{carboidratos:.1f}g")
                c4.metric("🥑 Gorduras", f"{gorduras:.1f}g")
                c5.metric("🌾 Fibras", f"{fibras:.1f}g")

                salvar_refeicao(
                    user["id"], str(data_refeicao),
                    descricao or "Refeição",
                    calorias, proteinas, carboidratos, gorduras, fibras, analise
                )
                st.success("💾 Refeição salva no diário!")

            except Exception as e:
                st.error(f"❌ Erro: {str(e)}")

# ── ABA 2: Diário ────────────────────────────────────────────
with aba2:
    st.subheader("📅 Diário Alimentar")

    data_filtro = st.date_input("Ver refeições do dia", value=date.today(), key="filtro_data", format="DD/MM/YYYY")
    df_dia = carregar_refeicoes(user["id"], str(data_filtro))

    if df_dia.empty:
        st.info("Nenhuma refeição registrada neste dia.")
    else:
        st.subheader("Totais do dia")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("🔥 Calorias", f"{df_dia['calorias'].sum():.0f} kcal")
        c2.metric("💪 Proteínas", f"{df_dia['proteinas'].sum():.1f}g")
        c3.metric("🍞 Carboidratos", f"{df_dia['carboidratos'].sum():.1f}g")
        c4.metric("🥑 Gorduras", f"{df_dia['gorduras'].sum():.1f}g")
        c5.metric("🌾 Fibras", f"{df_dia['fibras'].sum():.1f}g")
        st.divider()

        for _, row in df_dia.iterrows():
            with st.expander(f"🍽️ {row['descricao']} — {row['calorias']:.0f} kcal"):
                st.markdown(row["analise_completa"])
                if st.button("🗑️ Deletar", key=f"del_{row['id']}"):
                    deletar_refeicao(row["id"])
                    st.rerun()

# ── ABA 3: Gráficos ──────────────────────────────────────────
with aba3:
    st.subheader("📊 Evolução dos Macros")
    df_totais = carregar_totais_por_dia(user["id"])

    if df_totais.empty:
        st.info("Registre pelo menos uma refeição para ver os gráficos.")
    else:
        fig_cal = px.bar(
            df_totais, x="data", y="calorias",
            title="🔥 Calorias por Dia",
            labels={"data": "Data", "calorias": "Calorias (kcal)"},
            color="calorias", color_continuous_scale="Oranges"
        )
        st.plotly_chart(fig_cal, use_container_width=True)

        fig_macros = go.Figure()
        fig_macros.add_trace(go.Scatter(x=df_totais["data"], y=df_totais["proteinas"], mode="lines+markers", name="Proteínas (g)", line=dict(color="#4CAF50")))
        fig_macros.add_trace(go.Scatter(x=df_totais["data"], y=df_totais["carboidratos"], mode="lines+markers", name="Carboidratos (g)", line=dict(color="#2196F3")))
        fig_macros.add_trace(go.Scatter(x=df_totais["data"], y=df_totais["gorduras"], mode="lines+markers", name="Gorduras (g)", line=dict(color="#FF9800")))
        fig_macros.add_trace(go.Scatter(x=df_totais["data"], y=df_totais["fibras"], mode="lines+markers", name="Fibras (g)", line=dict(color="#9C27B0")))
        fig_macros.update_layout(title="📈 Macronutrientes ao Longo do Tempo", xaxis_title="Data", yaxis_title="Gramas (g)")
        st.plotly_chart(fig_macros, use_container_width=True)

        st.subheader("Médias do período")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("🔥 Média Calorias", f"{df_totais['calorias'].mean():.0f} kcal/dia")
        c2.metric("💪 Média Proteínas", f"{df_totais['proteinas'].mean():.1f}g/dia")
        c3.metric("🍞 Média Carboidratos", f"{df_totais['carboidratos'].mean():.1f}g/dia")
        c4.metric("🥑 Média Gorduras", f"{df_totais['gorduras'].mean():.1f}g/dia")
        c5.metric("🌾 Média Fibras", f"{df_totais['fibras'].mean():.1f}g/dia")