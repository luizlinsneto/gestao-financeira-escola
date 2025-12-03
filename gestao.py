import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os

# Configuração da Página
st.set_page_config(page_title="Gestão Financeira Escolar - PDDE", layout="wide")

# --- ESTILOS CSS ---
st.markdown(
    """
    <style>
    .stNumberInput input { text-align: right; }
    .big-font { font-size: 18px !important; font-weight: bold; }
    div[data-testid="stMetricValue"] { font-size: 24px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- CONEXÃO COM FIREBASE ---
def init_firebase():
    # Verifica se já foi inicializado para não dar erro ao recarregar a página
    if not firebase_admin._apps:
        cred = None

        # 1. Tenta pegar dos Segredos do Streamlit (apenas se estiver na nuvem)
        try:
            if "firebase" in st.secrets:
                cred_info = dict(st.secrets["firebase"])
                cred = credentials.Certificate(cred_info)
        except Exception:
            pass

        # 2. Se não achou na nuvem, tenta pegar de arquivo local (seu computador)
        if cred is None and os.path.exists("firebase_key.json"):
            try:
                cred = credentials.Certificate("firebase_key.json")
            except Exception as e:
                st.error(f"Erro ao ler o arquivo json: {e}")
                st.stop()

        # Inicializa se encontrou alguma credencial
        if cred:
            firebase_admin.initialize_app(cred)
        else:
            # Se não achar nada, avisa o usuário
            st.warning("⚠️ Atenção: Banco de dados não conectado.")
            st.info(
                "Certifique-se de que o arquivo 'firebase_key.json' está na mesma pasta do 'gestao.py' ou configure os Secrets na nuvem."
            )
            return None

    return firestore.client()


# --- FUNÇÕES DE BANCO DE DADOS (CRUD) ---


def load_data_from_firebase(db):
    """Carrega todas as contas do Firestore para a memória"""
    if db is None:
        return {}

    try:
        accounts_ref = db.collection("pdde_contas")
        docs = accounts_ref.stream()
        dados_carregados = {}
        for doc in docs:
            dados_carregados[doc.id] = doc.to_dict()
        return dados_carregados
    except Exception as e:
        st.error(f"Erro ao ler banco de dados: {e}")
        return {}


def save_account_to_firebase(db, account_name, account_data):
    """Salva os dados de uma conta específica no Firestore"""
    if db is None:
        st.warning("Dados salvos apenas temporariamente (sem conexão com banco).")
        return

    try:
        db.collection("pdde_contas").document(account_name).set(account_data)
    except Exception as e:
        st.error(f"Erro ao salvar no banco: {e}")


# --- FUNÇÕES AUXILIARES ---


def format_currency(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def init_session_state():
    # Inicializa conexão
    db = init_firebase()
    st.session_state["db_conn"] = db

    # Se conseguiu conectar, carrega do banco. Se não, inicia vazio.
    if db:
        st.session_state["accounts"] = load_data_from_firebase(db)
    elif "accounts" not in st.session_state:
        st.session_state["accounts"] = {}

    if "available_years" not in st.session_state:
        current_year = datetime.now().year
        # Tenta descobrir os anos que já existem nos dados
        anos_encontrados = set([current_year])
        for conta in st.session_state["accounts"].values():
            for mov in conta.get("movimentacoes", []):
                anos_encontrados.add(mov.get("ano", current_year))

        st.session_state["available_years"] = sorted(list(anos_encontrados))


def get_saldo_anterior(account_name, programa, tipo_recurso, mes_alvo, ano_alvo):
    """Calcula o saldo acumulado até o mês anterior."""
    conta_data = st.session_state["accounts"][account_name]
    movs = conta_data.get("movimentacoes", [])

    saldo = 0.0
    saldos_iniciais = conta_data.get("saldos_iniciais", {})

    # Soma Saldo Inicial Manual
    if programa in saldos_iniciais:
        if tipo_recurso == "Capital":
            saldo += saldos_iniciais[programa].get("Capital", 0.0)
        elif tipo_recurso == "Custeio":
            saldo += saldos_iniciais[programa].get("Custeio", 0.0)
        elif tipo_recurso == "Total":
            saldo += saldos_iniciais[programa].get("Capital", 0.0) + saldos_iniciais[
                programa
            ].get("Custeio", 0.0)

    # Soma Movimentações Anteriores
    for mov in movs:
        mov_ano = mov.get("ano", datetime.now().year)
        mov_mes = mov["mes_num"]

        eh_passado = (mov_ano < ano_alvo) or (
            mov_ano == ano_alvo and mov_mes < mes_alvo
        )

        if mov["programa"] == programa and eh_passado:
            if tipo_recurso == "Capital":
                saldo += (
                    mov["credito_capital"]
                    + mov["rendimento_capital"]
                    - mov["debito_capital"]
                )
            elif tipo_recurso == "Custeio":
                saldo += (
                    mov["credito_custeio"]
                    + mov["rendimento_custeio"]
                    - mov["debito_custeio"]
                )
            elif tipo_recurso == "Total":
                saldo += (
                    mov["total_credito"] + mov["total_rendimento"] - mov["total_debito"]
                )

    return saldo


# --- BARRA LATERAL (CONFIGURAÇÃO GERAL) ---
def sidebar_config():
    st.sidebar.header("⚙️ Configurações Gerais")

    with st.sidebar.expander("1. Cadastrar Nova Conta"):
        nova_conta = st.text_input("Número da Conta / Nome", placeholder="Ex: 27.922-6")
        if st.button("Adicionar Conta"):
            if nova_conta and nova_conta not in st.session_state["accounts"]:
                nova_estrutura = {
                    "programas": [],
                    "movimentacoes": [],
                    "saldos_iniciais": {},
                }
                # Atualiza Local e Banco
                st.session_state["accounts"][nova_conta] = nova_estrutura
                save_account_to_firebase(
                    st.session_state["db_conn"], nova_conta, nova_estrutura
                )

                st.success(f"Conta {nova_conta} criada!")
                st.rerun()
            elif nova_conta in st.session_state["accounts"]:
                st.warning("Conta já existe.")

    with st.sidebar.expander("2. Gerenciar Exercícios (Anos)"):
        novo_ano = st.number_input(
            "Adicionar Ano",
            min_value=2000,
            max_value=2050,
            value=datetime.now().year + 1,
            step=1,
        )
        if st.button("Criar Novo Exercício"):
            if novo_ano not in st.session_state["available_years"]:
                st.session_state["available_years"].append(novo_ano)
                st.session_state["available_years"].sort()
                st.success(f"Exercício de {novo_ano} adicionado!")
                st.rerun()
            else:
                st.warning("Este ano já existe.")


# --- LÓGICA DE CÁLCULO DE RENDIMENTO ---
def calcular_rateio_rendimento(
    conta, mes_num, ano, rendimento_total_banco, dados_entrada
):
    saldos_base = {}
    total_saldo_conta = 0.0

    for prog, valores in dados_entrada.items():
        saldo_ant_cap = get_saldo_anterior(conta, prog, "Capital", mes_num, ano)
        saldo_ant_cus = get_saldo_anterior(conta, prog, "Custeio", mes_num, ano)

        base_cap = max(0, saldo_ant_cap + valores["cred_cap"] - valores["deb_cap"])
        base_cus = max(0, saldo_ant_cus + valores["cred_cus"] - valores["deb_cus"])

        saldos_base[prog] = {"Capital": base_cap, "Custeio": base_cus}
        total_saldo_conta += base_cap + base_cus

    resultados = []

    for prog, valores in dados_entrada.items():
        base_prog = saldos_base[prog]

        if total_saldo_conta > 0:
            fator_cap = base_prog["Capital"] / total_saldo_conta
            fator_cus = base_prog["Custeio"] / total_saldo_conta
        else:
            fator_cap = 0
            fator_cus = 0

        rend_cap = rendimento_total_banco * fator_cap
        rend_cus = rendimento_total_banco * fator_cus

        resultados.append(
            {
                "programa": prog,
                "mes_num": mes_num,
                "ano": ano,
                "credito_capital": valores["cred_cap"],
                "credito_custeio": valores["cred_cus"],
                "debito_capital": valores["deb_cap"],
                "debito_custeio": valores["deb_cus"],
                "rendimento_capital": rend_cap,
                "rendimento_custeio": rend_cus,
                "total_credito": valores["cred_cap"] + valores["cred_cus"],
                "total_debito": valores["deb_cap"] + valores["deb_cus"],
                "total_rendimento": rend_cap + rend_cus,
            }
        )

    return resultados


# --- RENDERIZAÇÃO DA ABA DE ANO ---
def render_year_view(conta_atual, ano_atual, programas):
    tab_lanc, tab_rel = st.tabs(["📝 Lançamentos", "📑 Relatórios"])

    # --- ABA DE LANÇAMENTOS ---
    with tab_lanc:
        col_mes, col_rend = st.columns([1, 2])
        meses = {
            1: "Janeiro",
            2: "Fevereiro",
            3: "Março",
            4: "Abril",
            5: "Maio",
            6: "Junho",
            7: "Julho",
            8: "Agosto",
            9: "Setembro",
            10: "Outubro",
            11: "Novembro",
            12: "Dezembro",
        }

        with col_mes:
            mes_selecionado = st.selectbox(
                "Mês",
                options=list(meses.keys()),
                format_func=lambda x: meses[x],
                key=f"sel_mes_{conta_atual}_{ano_atual}",
            )

        movs = st.session_state["accounts"][conta_atual].get("movimentacoes", [])
        registros_existentes = [
            m
            for m in movs
            if m["mes_num"] == mes_selecionado
            and m.get("ano", datetime.now().year) == ano_atual
        ]

        val_rendimento_inicial = 0.0
        if registros_existentes:
            val_rendimento_inicial = sum(
                [m["total_rendimento"] for m in registros_existentes]
            )
            st.info(f"✏️ Editando dados já salvos de {meses[mes_selecionado]}.")

        with col_rend:
            rendimento_total = st.number_input(
                "💰 Rendimento/Ajuste (Total Extrato)",
                value=float(val_rendimento_inicial),
                step=0.01,
                format="%.2f",
                key=f"rend_tot_{conta_atual}_{ano_atual}_{mes_selecionado}",
            )
            st.caption("Valor total do rendimento (positivo) ou ajuste (negativo).")

        st.divider()

        dados_entrada = {}
        for prog in programas:
            prog_data = next(
                (m for m in registros_existentes if m["programa"] == prog), None
            )

            v_cc = float(prog_data["credito_capital"]) if prog_data else 0.0
            v_crc = float(prog_data["credito_custeio"]) if prog_data else 0.0
            v_dc = float(prog_data["debito_capital"]) if prog_data else 0.0
            v_dec = float(prog_data["debito_custeio"]) if prog_data else 0.0

            with st.expander(f"Movimento: {prog}", expanded=True):
                c1, c2, c3, c4 = st.columns(4)

                saldo_ant_cap = get_saldo_anterior(
                    conta_atual, prog, "Capital", mes_selecionado, ano_atual
                )
                saldo_ant_cus = get_saldo_anterior(
                    conta_atual, prog, "Custeio", mes_selecionado, ano_atual
                )

                st.markdown(
                    f"**Saldo Ant.:** Cap: {format_currency(saldo_ant_cap)} | Cust: {format_currency(saldo_ant_cus)}"
                )

                k_suf = f"{conta_atual}_{prog}_{ano_atual}_{mes_selecionado}"

                cred_cap = c1.number_input(
                    f"Créd. Capital", min_value=0.0, value=v_cc, key=f"cc_{k_suf}"
                )
                cred_cus = c2.number_input(
                    f"Créd. Custeio", min_value=0.0, value=v_crc, key=f"crc_{k_suf}"
                )
                deb_cap = c3.number_input(
                    f"Déb. Capital", min_value=0.0, value=v_dc, key=f"dc_{k_suf}"
                )
                deb_cus = c4.number_input(
                    f"Déb. Custeio", min_value=0.0, value=v_dec, key=f"dec_{k_suf}"
                )

                dados_entrada[prog] = {
                    "cred_cap": cred_cap,
                    "cred_cus": cred_cus,
                    "deb_cap": deb_cap,
                    "deb_cus": deb_cus,
                }

        if st.button(
            f"💾 Salvar Lançamento {meses[mes_selecionado]}/{ano_atual}",
            type="primary",
            key=f"btn_save_{conta_atual}_{ano_atual}_{mes_selecionado}",
        ):
            novos_registros = calcular_rateio_rendimento(
                conta_atual, mes_selecionado, ano_atual, rendimento_total, dados_entrada
            )

            lista_atual = st.session_state["accounts"][conta_atual].get(
                "movimentacoes", []
            )
            lista_limpa = [
                m
                for m in lista_atual
                if not (
                    m["mes_num"] == mes_selecionado
                    and m.get("ano", datetime.now().year) == ano_atual
                )
            ]
            lista_limpa.extend(novos_registros)

            st.session_state["accounts"][conta_atual]["movimentacoes"] = lista_limpa

            # SALVA NO FIREBASE
            save_account_to_firebase(
                st.session_state["db_conn"],
                conta_atual,
                st.session_state["accounts"][conta_atual],
            )

            st.success(f"Dados salvos com sucesso!")
            st.rerun()

    # --- ABA DE RELATÓRIOS ---
    with tab_rel:
        st.subheader(f"Extrato - {conta_atual} ({ano_atual})")
        filtro_prog = st.selectbox(
            "Filtrar Programa",
            ["Todos"] + programas,
            key=f"filt_prog_{conta_atual}_{ano_atual}",
        )

        movs = st.session_state["accounts"][conta_atual].get("movimentacoes", [])

        programas_para_listar = programas if filtro_prog == "Todos" else [filtro_prog]

        df_final = pd.DataFrame()

        for p in programas_para_listar:
            dados_tabela = []

            saldo_acumulado_cap = get_saldo_anterior(
                conta_atual, p, "Capital", 1, ano_atual
            )
            saldo_acumulado_cus = get_saldo_anterior(
                conta_atual, p, "Custeio", 1, ano_atual
            )

            movs_prog_ano = [
                m
                for m in movs
                if m["programa"] == p and m.get("ano", datetime.now().year) == ano_atual
            ]
            movs_prog_ano.sort(key=lambda x: x["mes_num"])

            for m in movs_prog_ano:
                saldo_acumulado_cap += (
                    m["credito_capital"] + m["rendimento_capital"] - m["debito_capital"]
                )
                saldo_acumulado_cus += (
                    m["credito_custeio"] + m["rendimento_custeio"] - m["debito_custeio"]
                )
                saldo_total = saldo_acumulado_cap + saldo_acumulado_cus

                # ADICIONADO: Colunas separadas de rendimento
                dados_tabela.append(
                    {
                        "Programa": p,
                        "Mês": meses[m["mes_num"]],
                        "Crédito": m["total_credito"],
                        "Rend. Cap.": m["rendimento_capital"],
                        "Rend. Cust.": m["rendimento_custeio"],
                        "Rend. Total": m["total_rendimento"],
                        "Débito": m["total_debito"],
                        "S. Custeio": saldo_acumulado_cus,
                        "S. Capital": saldo_acumulado_cap,
                        "S. Total": saldo_total,
                    }
                )

            if dados_tabela:
                df_prog = pd.DataFrame(dados_tabela)

                total_credito = df_prog["Crédito"].sum()
                total_rend_cap = df_prog["Rend. Cap."].sum()
                total_rend_cus = df_prog["Rend. Cust."].sum()
                total_rendimento = df_prog["Rend. Total"].sum()
                total_debito = df_prog["Débito"].sum()

                ultimo_cus = df_prog["S. Custeio"].iloc[-1]
                ultimo_cap = df_prog["S. Capital"].iloc[-1]
                ultimo_total = df_prog["S. Total"].iloc[-1]

                linha_total = pd.DataFrame(
                    [
                        {
                            "Programa": "TOTAL",
                            "Mês": "---",
                            "Crédito": total_credito,
                            "Rend. Cap.": total_rend_cap,
                            "Rend. Cust.": total_rend_cus,
                            "Rend. Total": total_rendimento,
                            "Débito": total_debito,
                            "S. Custeio": ultimo_cus,
                            "S. Capital": ultimo_cap,
                            "S. Total": ultimo_total,
                        }
                    ]
                )

                df_prog = pd.concat([df_prog, linha_total], ignore_index=True)
                df_final = pd.concat([df_final, df_prog], ignore_index=True)

        if not df_final.empty:

            def highlight_total(row):
                if row["Programa"] == "TOTAL":
                    return [
                        "background-color: #ffd700; color: black; font-weight: bold"
                    ] * len(row)
                return [""] * len(row)

            # ATUALIZADO: Formatação para incluir as novas colunas
            st.dataframe(
                df_final.style.format(
                    {
                        "Crédito": "R$ {:,.2f}",
                        "Rend. Cap.": "R$ {:,.2f}",
                        "Rend. Cust.": "R$ {:,.2f}",
                        "Rend. Total": "R$ {:,.2f}",
                        "Débito": "R$ {:,.2f}",
                        "S. Custeio": "R$ {:,.2f}",
                        "S. Capital": "R$ {:,.2f}",
                        "S. Total": "R$ {:,.2f}",
                    }
                ).apply(highlight_total, axis=1),
                use_container_width=True,
                height=500,
            )
        else:
            st.info(f"Nenhuma movimentação em {ano_atual}.")


# --- INTERFACE PRINCIPAL ---
def main():
    init_session_state()
    sidebar_config()

    st.title("📊 Controle Financeiro - PDDE")

    contas_existentes = list(st.session_state["accounts"].keys())

    if not contas_existentes:
        st.info("👈 Comece cadastrando uma nova conta bancária na barra lateral.")
        return

    tabs_contas = st.tabs(contas_existentes)

    for aba, conta_nome in zip(tabs_contas, contas_existentes):
        with aba:
            st.header(f"Conta: {conta_nome}")

            with st.expander("⚙️ Gerenciar Programas e Saldos Iniciais"):
                st.info(
                    "Dica: Use 'Saldo Inicial' se você já tem dinheiro na conta antes de começar a usar este sistema."
                )

                c_add1, c_add2 = st.columns([3, 1])
                novo_prog = c_add1.text_input(
                    "Novo Programa",
                    placeholder="Ex: PDDE Qualidade",
                    key=f"new_prog_{conta_nome}",
                )
                if c_add2.button("Adicionar", key=f"btn_add_prog_{conta_nome}"):
                    conta_dados = st.session_state["accounts"][conta_nome]
                    progs = conta_dados.get("programas", [])

                    if novo_prog and novo_prog not in progs:
                        progs.append(novo_prog)
                        conta_dados["programas"] = progs

                        if "saldos_iniciais" not in conta_dados:
                            conta_dados["saldos_iniciais"] = {}
                        conta_dados["saldos_iniciais"][novo_prog] = {
                            "Capital": 0.0,
                            "Custeio": 0.0,
                        }

                        save_account_to_firebase(
                            st.session_state["db_conn"], conta_nome, conta_dados
                        )

                        st.success("Adicionado!")
                        st.rerun()

                progs_atuais = st.session_state["accounts"][conta_nome].get(
                    "programas", []
                )
                if progs_atuais:
                    st.write("---")
                    st.write("**Saldos Iniciais (Abertura de Conta):**")
                    for p in progs_atuais:
                        conta_dados = st.session_state["accounts"][conta_nome]
                        if "saldos_iniciais" not in conta_dados:
                            conta_dados["saldos_iniciais"] = {}
                        if p not in conta_dados["saldos_iniciais"]:
                            conta_dados["saldos_iniciais"][p] = {
                                "Capital": 0.0,
                                "Custeio": 0.0,
                            }

                        cols = st.columns([2, 1, 1, 1])
                        cols[0].write(f"📂 {p}")

                        val_cap = conta_dados["saldos_iniciais"][p]["Capital"]
                        val_cus = conta_dados["saldos_iniciais"][p]["Custeio"]

                        novo_val_cap = cols[1].number_input(
                            f"Saldo Inicial Capital",
                            value=val_cap,
                            key=f"si_cap_{conta_nome}_{p}",
                        )
                        novo_val_cus = cols[2].number_input(
                            f"Saldo Inicial Custeio",
                            value=val_cus,
                            key=f"si_cus_{conta_nome}_{p}",
                        )

                        if cols[3].button(
                            "Atualizar Saldo Inicial", key=f"btn_si_{conta_nome}_{p}"
                        ):
                            conta_dados["saldos_iniciais"][p]["Capital"] = novo_val_cap
                            conta_dados["saldos_iniciais"][p]["Custeio"] = novo_val_cus

                            save_account_to_firebase(
                                st.session_state["db_conn"], conta_nome, conta_dados
                            )

                            st.success("Saldo inicial atualizado!")
                            st.rerun()

            if not st.session_state["accounts"][conta_nome].get("programas"):
                st.warning("Adicione programas acima para começar.")
            else:
                if (
                    "available_years" in st.session_state
                    and st.session_state["available_years"]
                ):
                    anos_disponiveis = sorted(st.session_state["available_years"])
                else:
                    anos_disponiveis = [datetime.now().year]

                titulos_abas_anos = [str(a) for a in anos_disponiveis]
                abas_anos = st.tabs(titulos_abas_anos)

                for i_ano, aba_ano in enumerate(abas_anos):
                    ano = anos_disponiveis[i_ano]
                    with aba_ano:
                        render_year_view(
                            conta_nome,
                            ano,
                            st.session_state["accounts"][conta_nome]["programas"],
                        )


if __name__ == "__main__":
    main()
