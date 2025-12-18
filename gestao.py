import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os
import base64

# Configuração da Página
st.set_page_config(
    page_title="Gestão Financeira Escolar - PDDE", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .stNumberInput input { text-align: right; }
    .big-font { font-size: 18px !important; font-weight: bold; }
    div[data-testid="stMetricValue"] { font-size: 24px; }
    .download-box {
        padding: 15px;
        background-color: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-radius: 8px;
        margin-bottom: 10px;
    }
    .row-header { font-weight: bold; border-bottom: 2px solid #ddd; padding: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- CONEXÃO COM FIREBASE ---


@st.cache_resource
def init_firebase():
    """Inicializa a conexão com Firebase apenas uma vez e mantém em cache."""
    if not firebase_admin._apps:
        cred = None
        if os.path.exists("firebase_key.json"):
            try:
                cred = credentials.Certificate("firebase_key.json")
            except Exception as e:
                st.error(f"Erro no arquivo json: {e}")
                return None
        else:
            try:
                if hasattr(st, "secrets") and "firebase" in st.secrets:
                    cred_info = dict(st.secrets["firebase"])
                    cred = credentials.Certificate(cred_info)
            except Exception:
                pass

        if cred:
            firebase_admin.initialize_app(cred)
            return firestore.client()
        else:
            return None
    return firestore.client()

# --- FUNÇÕES DE BANCO DE DADOS (CRUD) ---


def load_accounts_from_firebase(db):
    if db is None:
        return {}
    try:
        accounts_ref = db.collection('pdde_contas')
        docs = accounts_ref.stream()
        dados = {}
        for doc in docs:
            dados[doc.id] = doc.to_dict()
        return dados
    except Exception as e:
        st.error(f"Erro ao ler contas: {e}")
        return {}


def load_empenhos_from_firebase(db):
    if db is None:
        return []
    try:
        doc = db.collection('pdde_dados_gerais').document('empenhos').get()
        if doc.exists:
            return doc.to_dict().get('lista', [])
        return []
    except Exception as e:
        return []


def load_global_programs_from_firebase(db):
    if db is None:
        return []
    try:
        doc = db.collection('pdde_dados_gerais').document(
            'programas_globais').get()
        if doc.exists:
            return doc.to_dict().get('lista', [])
        return []
    except Exception as e:
        return []

# --- FUNÇÕES PARA ARQUIVOS ---


def save_file_to_firebase(db, empenho_id, file_obj):
    if db is None or file_obj is None:
        return
    try:
        if file_obj.size > 2 * 1024 * 1024:
            st.error("Arquivo muito grande! O limite recomendado é 2MB.")
            return False
        file_bytes = file_obj.read()
        b64_string = base64.b64encode(file_bytes).decode('utf-8')
        db.collection('pdde_arquivos').document(empenho_id).set({
            'file_name': file_obj.name,
            'file_data': b64_string
        })
        return True
    except Exception as e:
        st.error(f"Erro ao salvar arquivo: {e}")
        return False


def get_file_from_firebase(db, empenho_id):
    if db is None:
        return None
    try:
        doc = db.collection('pdde_arquivos').document(empenho_id).get()
        if doc.exists:
            return doc.to_dict()
        return None
    except:
        return None


def delete_file_from_firebase(db, empenho_id):
    if db is None:
        return
    try:
        db.collection('pdde_arquivos').document(empenho_id).delete()
    except:
        pass

# --- FUNÇÕES DE SALVAMENTO ---


def save_account_to_firebase(db, account_name, account_data):
    if db is None:
        return
    try:
        db.collection('pdde_contas').document(account_name).set(account_data)
    except Exception as e:
        st.error(f"Erro ao salvar conta: {e}")


def delete_account_from_firebase(db, account_name):
    if db is None:
        return
    try:
        db.collection('pdde_contas').document(account_name).delete()
    except Exception as e:
        st.error(f"Erro ao excluir conta: {e}")


def rename_account_in_firebase(db, old_name, new_name):
    if db is None:
        return False
    try:
        new_ref = db.collection('pdde_contas').document(new_name)
        if new_ref.get().exists:
            st.warning(f"Já existe uma conta com o nome '{new_name}'.")
            return False
        old_ref = db.collection('pdde_contas').document(old_name)
        doc = old_ref.get()
        if not doc.exists:
            return False
        data = doc.to_dict()
        new_ref.set(data)
        old_ref.delete()
        return True
    except Exception as e:
        st.error(f"Erro ao renomear: {e}")
        return False


def save_empenhos_to_firebase(db, lista_empenhos):
    if db is None:
        return
    try:
        db.collection('pdde_dados_gerais').document(
            'empenhos').set({'lista': lista_empenhos})
    except Exception as e:
        st.error(f"Erro ao salvar empenhos: {e}")


def save_global_programs_to_firebase(db, lista_programas):
    if db is None:
        return
    try:
        db.collection('pdde_dados_gerais').document(
            'programas_globais').set({'lista': lista_programas})
    except Exception as e:
        st.error(f"Erro ao salvar programas globais: {e}")

# --- FUNÇÕES AUXILIARES ---


def format_currency(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def init_session_state():
    db = init_firebase()
    st.session_state['db_conn'] = db

    if 'accounts' not in st.session_state:
        if db:
            with st.spinner('Conectando ao banco de dados...'):
                st.session_state['accounts'] = load_accounts_from_firebase(db)
        else:
            st.session_state['accounts'] = {}

    if 'empenhos_global' not in st.session_state:
        if db:
            st.session_state['empenhos_global'] = load_empenhos_from_firebase(
                db)
        else:
            st.session_state['empenhos_global'] = []

    if 'global_programs' not in st.session_state:
        if db:
            st.session_state['global_programs'] = load_global_programs_from_firebase(
                db)
        else:
            st.session_state['global_programs'] = []

    if 'available_years' not in st.session_state:
        current_year = datetime.now().year
        anos_encontrados = set([current_year])
        for conta in st.session_state['accounts'].values():
            for mov in conta.get('movimentacoes', []):
                anos_encontrados.add(mov.get('ano', current_year))
        for emp in st.session_state['empenhos_global']:
            try:
                dt = datetime.strptime(emp['data_empenho'], "%Y-%m-%d")
                anos_encontrados.add(dt.year)
            except:
                pass
        st.session_state['available_years'] = sorted(list(anos_encontrados))


def get_saldo_anterior(account_name, programa, tipo_recurso, mes_alvo, ano_alvo):
    conta_data = st.session_state['accounts'][account_name]
    movs = conta_data.get('movimentacoes', [])
    saldo = 0.0
    saldos_iniciais = conta_data.get('saldos_iniciais', {})

    if programa in saldos_iniciais:
        val = saldos_iniciais[programa].get(tipo_recurso, 0.0) if tipo_recurso != 'Total' else \
            saldos_iniciais[programa].get(
                'Capital', 0.0) + saldos_iniciais[programa].get('Custeio', 0.0)
        saldo += val

    for mov in movs:
        mov_ano = mov.get('ano', datetime.now().year)
        mov_mes = mov['mes_num']
        eh_passado = (mov_ano < ano_alvo) or (
            mov_ano == ano_alvo and mov_mes < mes_alvo)

        if mov['programa'] == programa and eh_passado:
            if tipo_recurso == 'Capital':
                saldo += (mov['credito_capital'] +
                          mov['rendimento_capital'] - mov['debito_capital'])
            elif tipo_recurso == 'Custeio':
                saldo += (mov['credito_custeio'] +
                          mov['rendimento_custeio'] - mov['debito_custeio'])
            elif tipo_recurso == 'Total':
                saldo += (mov['total_credito'] +
                          mov['total_rendimento'] - mov['total_debito'])
    return saldo

# --- BARRA LATERAL ---


def sidebar_config():
    if st.session_state['db_conn'] is None:
        st.sidebar.error("⚠️ Sem conexão com Banco de Dados")

    if st.sidebar.button("🔄 Recarregar Dados", help="Clique se os dados da barra lateral estiverem diferentes da tela principal"):
        st.cache_resource.clear()
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.sidebar.subheader("📍 Navegação")
    modulo_selecionado = st.sidebar.radio(
        "Módulo",
        ["🏦 Movimentação Financeira", "📜 Controle de Empenhos", "📈 Resumo Consolidado"],
        label_visibility="collapsed"
    )
    st.sidebar.divider()

    conta_selecionada = None

    if modulo_selecionado == "🏦 Movimentação Financeira":
        contas_existentes = sorted(list(st.session_state['accounts'].keys()))

        if contas_existentes:
            conta_selecionada = st.sidebar.selectbox(
                "📂 Selecione a Conta",
                options=contas_existentes,
                key="sidebar_conta_select"
            )

            dados_conta_atual = st.session_state['accounts'].get(
                conta_selecionada, {})
            progs_conta = dados_conta_atual.get('programas', [])

            if progs_conta:
                st.sidebar.markdown("**📌 Programas Vinculados:**")
                texto_progs = "\n".join([f"• {p}" for p in progs_conta])
                st.sidebar.text(texto_progs.replace("• ", ""))
            else:
                st.sidebar.caption("Nenhum programa vinculado.")
            st.sidebar.divider()

        with st.sidebar.expander("⚙️ Gerenciar Contas"):
            tab_criar, tab_renomear, tab_del = st.tabs(
                ["Criar", "Renomear", "Excluir"])

            with tab_criar:
                nova_conta = st.text_input(
                    "Nome da Nova Conta", placeholder="Ex: 27.922-6")
                if st.button("Adicionar Conta"):
                    if nova_conta and nova_conta not in st.session_state['accounts']:
                        nova_estrutura = {
                            'programas': [], 'movimentacoes': [], 'saldos_iniciais': {}}
                        st.session_state['accounts'][nova_conta] = nova_estrutura
                        save_account_to_firebase(
                            st.session_state['db_conn'], nova_conta, nova_estrutura)
                        st.success(f"Conta {nova_conta} criada!")
                        st.rerun()
                    elif nova_conta in st.session_state['accounts']:
                        st.warning("Conta já existe.")

            with tab_renomear:
                if contas_existentes:
                    conta_alvo = st.selectbox(
                        "Conta Atual:", contas_existentes, key="sel_ren_acc")
                    novo_nome_conta = st.text_input(
                        "Novo Nome:", key="ipt_ren_acc")

                    if st.button("✏️ Renomear", type="primary"):
                        if novo_nome_conta and novo_nome_conta not in contas_existentes:
                            success = rename_account_in_firebase(
                                st.session_state['db_conn'], conta_alvo, novo_nome_conta)
                            if success:
                                if conta_alvo in st.session_state['accounts']:
                                    dados = st.session_state['accounts'].pop(
                                        conta_alvo)
                                    st.session_state['accounts'][novo_nome_conta] = dados
                                    st.success(
                                        f"Renomeado para {novo_nome_conta}!")
                                    st.rerun()
                        elif novo_nome_conta in contas_existentes:
                            st.warning("Nome já existe!")
                else:
                    st.info("Sem contas.")

            with tab_del:
                if contas_existentes:
                    conta_del = st.selectbox(
                        "Apagar Conta:", contas_existentes, key="sel_del_acc")
                    if st.button(f"🗑️ Excluir {conta_del}", type="primary"):
                        if conta_del in st.session_state['accounts']:
                            del st.session_state['accounts'][conta_del]
                            delete_account_from_firebase(
                                st.session_state['db_conn'], conta_del)
                            st.success(f"Conta {conta_del} excluída!")
                            st.rerun()
                else:
                    st.info("Nenhuma conta para excluir.")

    with st.sidebar.expander("📅 Gerenciar Exercícios (Anos)"):
        novo_ano = st.number_input(
            "Adicionar Ano", min_value=2000, max_value=2050, value=datetime.now().year + 1, step=1)
        if st.button("Criar Novo Exercício"):
            if novo_ano not in st.session_state['available_years']:
                st.session_state['available_years'].append(novo_ano)
                st.session_state['available_years'].sort()
                st.success(f"Exercício de {novo_ano} adicionado!")
                st.rerun()
            else:
                st.warning("Este ano já existe.")

    return modulo_selecionado, conta_selecionada


def calcular_rateio_rendimento(conta, mes_num, ano, rendimento_total_banco, dados_entrada):
    saldos_base = {}
    total_saldo_conta = 0.0
    for prog, valores in dados_entrada.items():
        saldo_ant_cap = get_saldo_anterior(
            conta, prog, 'Capital', mes_num, ano)
        saldo_ant_cus = get_saldo_anterior(
            conta, prog, 'Custeio', mes_num, ano)
        base_cap = max(0, saldo_ant_cap +
                       valores['cred_cap'] - valores['deb_cap'])
        base_cus = max(0, saldo_ant_cus +
                       valores['cred_cus'] - valores['deb_cus'])
        saldos_base[prog] = {'Capital': base_cap, 'Custeio': base_cus}
        total_saldo_conta += (base_cap + base_cus)

    resultados = []
    for prog, valores in dados_entrada.items():
        base_prog = saldos_base[prog]
        fator_cap = base_prog['Capital'] / \
            total_saldo_conta if total_saldo_conta > 0 else 0
        fator_cus = base_prog['Custeio'] / \
            total_saldo_conta if total_saldo_conta > 0 else 0

        rend_cap = rendimento_total_banco * fator_cap
        rend_cus = rendimento_total_banco * fator_cus

        resultados.append({
            'programa': prog, 'mes_num': mes_num, 'ano': ano,
            'credito_capital': valores['cred_cap'], 'credito_custeio': valores['cred_cus'],
            'debito_capital': valores['deb_cap'], 'debito_custeio': valores['deb_cus'],
            'rendimento_capital': rend_cap, 'rendimento_custeio': rend_cus,
            'total_credito': valores['cred_cap'] + valores['cred_cus'],
            'total_debito': valores['deb_cap'] + valores['deb_cus'],
            'total_rendimento': rend_cap + rend_cus
        })
    return resultados

# === VISUALIZAÇÃO 1: MÓDULO FINANCEIRO ===


def render_financeiro_view(conta_atual, ano_atual, programas):
    tab_lanc, tab_rel, tab_resumo = st.tabs(
        ["📝 Lançamentos", "📑 Extrato Mensal", "📊 Resumo Anual"])

    with tab_lanc:
        col_mes, col_rend = st.columns([1, 2])
        meses = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
                 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}

        with col_mes:
            mes_selecionado = st.selectbox("Mês", options=list(meses.keys(
            )), format_func=lambda x: meses[x], key=f"sel_mes_{conta_atual}_{ano_atual}")

        movs = st.session_state['accounts'][conta_atual].get(
            'movimentacoes', [])
        registros_existentes = [m for m in movs if m['mes_num'] == mes_selecionado and m.get(
            'ano', datetime.now().year) == ano_atual]

        val_rendimento_inicial = 0.0
        if registros_existentes:
            val_rendimento_inicial = sum(
                [m['total_rendimento'] for m in registros_existentes])
            st.info(f"✏️ Editando dados de {meses[mes_selecionado]}.")

        with col_rend:
            rendimento_total = st.number_input(
                "💰 Rendimento/Ajuste (Total Extrato)",
                value=float(val_rendimento_inicial), step=0.01, format="%.2f",
                key=f"rend_tot_{conta_atual}_{ano_atual}_{mes_selecionado}"
            )

        st.divider()
        dados_entrada = {}
        has_error = False

        for prog in programas:
            prog_data = next(
                (m for m in registros_existentes if m['programa'] == prog), None)
            v_cc = float(prog_data['credito_capital']) if prog_data else 0.0
            v_crc = float(prog_data['credito_custeio']) if prog_data else 0.0
            v_dc = float(prog_data['debito_capital']) if prog_data else 0.0
            v_dec = float(prog_data['debito_custeio']) if prog_data else 0.0

            saldo_disp_cap = get_saldo_anterior(
                conta_atual, prog, 'Capital', mes_selecionado, ano_atual)
            saldo_disp_cust = get_saldo_anterior(
                conta_atual, prog, 'Custeio', mes_selecionado, ano_atual)

            with st.expander(f"Movimento: {prog}", expanded=True):
                c1, c2, c3, c4 = st.columns(4)

                st.markdown(
                    f"**Saldo Ant.:** Cap: {format_currency(saldo_disp_cap)} | Cust: {format_currency(saldo_disp_cust)}")

                k_suf = f"{conta_atual}_{prog}_{ano_atual}_{mes_selecionado}"
                cred_cap = c1.number_input(
                    f"Créd. Capital", min_value=0.0, value=v_cc, key=f"cc_{k_suf}")
                cred_cus = c2.number_input(
                    f"Créd. Custeio", min_value=0.0, value=v_crc, key=f"crc_{k_suf}")
                deb_cap = c3.number_input(
                    f"Déb. Capital", min_value=0.0, value=v_dc, key=f"dc_{k_suf}")
                deb_cus = c4.number_input(
                    f"Déb. Custeio", min_value=0.0, value=v_dec, key=f"dec_{k_suf}")

                saldo_proj_cap = saldo_disp_cap + cred_cap - deb_cap
                saldo_proj_cust = saldo_disp_cust + cred_cus - deb_cus

                if saldo_proj_cap < 0:
                    st.error(
                        f"⚠️ Atenção: Saldo de Capital ficará negativo ({format_currency(saldo_proj_cap)})!")
                    has_error = True

                if saldo_proj_cust < 0:
                    st.error(
                        f"⚠️ Atenção: Saldo de Custeio ficará negativo ({format_currency(saldo_proj_cust)})!")
                    has_error = True

                dados_entrada[prog] = {
                    'cred_cap': cred_cap, 'cred_cus': cred_cus, 'deb_cap': deb_cap, 'deb_cus': deb_cus}

        if st.button(f"💾 Salvar Lançamento {meses[mes_selecionado]}/{ano_atual}", type="primary", key=f"btn_save_{conta_atual}_{ano_atual}_{mes_selecionado}"):
            if has_error:
                st.error(
                    "❌ Não é possível salvar pois há saldos negativos. Verifique os valores de débito.")
            else:
                novos_registros = calcular_rateio_rendimento(
                    conta_atual, mes_selecionado, ano_atual, rendimento_total, dados_entrada)
                lista_atual = st.session_state['accounts'][conta_atual].get(
                    'movimentacoes', [])
                lista_limpa = [m for m in lista_atual if not (
                    m['mes_num'] == mes_selecionado and m.get('ano', datetime.now().year) == ano_atual)]
                lista_limpa.extend(novos_registros)
                st.session_state['accounts'][conta_atual]['movimentacoes'] = lista_limpa
                save_account_to_firebase(
                    st.session_state['db_conn'], conta_atual, st.session_state['accounts'][conta_atual])
                st.success("Dados salvos com sucesso!")
                st.rerun()

    with tab_rel:
        st.subheader(f"Extrato Mensal Detalhado - {ano_atual}")
        filtro_prog = st.selectbox("Filtrar Programa", [
                                   "Todos"] + programas, key=f"filt_prog_{conta_atual}_{ano_atual}")
        movs = st.session_state['accounts'][conta_atual].get(
            'movimentacoes', [])
        programas_para_listar = programas if filtro_prog == "Todos" else [
            filtro_prog]

        df_final = pd.DataFrame()
        for p in programas_para_listar:
            dados_tabela = []
            saldo_acumulado_cap = get_saldo_anterior(
                conta_atual, p, 'Capital', 1, ano_atual)
            saldo_acumulado_cus = get_saldo_anterior(
                conta_atual, p, 'Custeio', 1, ano_atual)

            movs_prog_ano = [m for m in movs if m['programa'] ==
                             p and m.get('ano', datetime.now().year) == ano_atual]
            movs_prog_ano.sort(key=lambda x: x['mes_num'])

            for m in movs_prog_ano:
                saldo_acumulado_cap += (m['credito_capital'] +
                                        m['rendimento_capital'] - m['debito_capital'])
                saldo_acumulado_cus += (m['credito_custeio'] +
                                        m['rendimento_custeio'] - m['debito_custeio'])
                saldo_total = saldo_acumulado_cap + saldo_acumulado_cus
                dados_tabela.append({
                    "Programa": p, "Mês": meses[m['mes_num']],
                    "Créd. Cap.": m['credito_capital'],
                    "Créd. Cust.": m['credito_custeio'],
                    "Créd. Total": m['total_credito'],
                    "Rend. Cap.": m['rendimento_capital'],
                    "Rend. Cust.": m['rendimento_custeio'],
                    "Rend. Total": m['total_rendimento'],
                    "Déb. Cap.": m['debito_capital'],
                    "Déb. Cust.": m['debito_custeio'],
                    "Déb. Total": m['total_debito'],
                    "S. Custeio": saldo_acumulado_cus,
                    "S. Capital": saldo_acumulado_cap, "S. Total": saldo_total
                })

            if dados_tabela:
                df_prog = pd.DataFrame(dados_tabela)
                linha_total = pd.DataFrame([{
                    "Programa": "TOTAL", "Mês": "---",
                    "Créd. Cap.": df_prog["Créd. Cap."].sum(), "Créd. Cust.": df_prog["Créd. Cust."].sum(), "Créd. Total": df_prog["Créd. Total"].sum(),
                    "Rend. Cap.": df_prog["Rend. Cap."].sum(), "Rend. Cust.": df_prog["Rend. Cust."].sum(), "Rend. Total": df_prog["Rend. Total"].sum(),
                    "Déb. Cap.": df_prog["Déb. Cap."].sum(), "Déb. Cust.": df_prog["Déb. Cust."].sum(), "Déb. Total": df_prog["Déb. Total"].sum(),
                    "S. Custeio": df_prog["S. Custeio"].iloc[-1], "S. Capital": df_prog["S. Capital"].iloc[-1], "S. Total": df_prog["S. Total"].iloc[-1]
                }])
                df_final = pd.concat(
                    [df_final, df_prog, linha_total], ignore_index=True)

        if not df_final.empty:
            def highlight_total(row):
                return ['background-color: #ffd700; color: black; font-weight: bold'] * len(row) if row['Programa'] == 'TOTAL' else [''] * len(row)

            st.dataframe(df_final.style.format({
                "Créd. Cap.": "R$ {:,.2f}", "Créd. Cust.": "R$ {:,.2f}", "Créd. Total": "R$ {:,.2f}",
                "Rend. Cap.": "R$ {:,.2f}", "Rend. Cust.": "R$ {:,.2f}",
                "Rend. Total": "R$ {:,.2f}", "Déb. Cap.": "R$ {:,.2f}", "Déb. Cust.": "R$ {:,.2f}", "Déb. Total": "R$ {:,.2f}",
                "S. Custeio": "R$ {:,.2f}", "S. Capital": "R$ {:,.2f}", "S. Total": "R$ {:,.2f}",
            }).apply(highlight_total, axis=1), use_container_width=True, height=500)
        else:
            st.info(f"Nenhuma movimentação em {ano_atual}.")

    with tab_resumo:
        # === MUDANÇA DE NOME SOLICITADA ===
        st.markdown("### 📊 Resumo Geral e Demonstrativo da Conta")
        st.divider()
        st.markdown("#### 📑 Simulação do Demonstrativo (Bloco 2)")
        prog_demo = st.selectbox("Selecione o Programa para Detalhar:",
                                 options=programas, key=f"sel_demo_{conta_atual}")

        if prog_demo:
            s_reprog_cust = get_saldo_anterior(
                conta_atual, prog_demo, 'Custeio', 1, ano_atual)
            s_reprog_cap = get_saldo_anterior(
                conta_atual, prog_demo, 'Capital', 1, ano_atual)

            movs = st.session_state['accounts'][conta_atual].get(
                'movimentacoes', [])
            movs_demo = [m for m in movs if m['programa']
                         == prog_demo and m.get('ano') == ano_atual]

            cred_cust = sum(m['credito_custeio'] for m in movs_demo)
            cred_cap = sum(m['credito_capital'] for m in movs_demo)
            rend_cust = sum(m['rendimento_custeio'] for m in movs_demo)
            rend_cap = sum(m['rendimento_capital'] for m in movs_demo)
            desp_cust = sum(m['debito_custeio'] for m in movs_demo)
            desp_cap = sum(m['debito_capital'] for m in movs_demo)

            rec_prop_cust = 0.0
            rec_prop_cap = 0.0
            devol_cust = 0.0
            devol_cap = 0.0

            total_rec_cust = s_reprog_cust + cred_cust + \
                rec_prop_cust + rend_cust - devol_cust
            total_rec_cap = s_reprog_cap + cred_cap + rec_prop_cap + rend_cap - devol_cap
            saldo_final_cust = total_rec_cust - desp_cust
            saldo_final_cap = total_rec_cap - desp_cap

            df_demo = pd.DataFrame([
                {"Descrição": "08 - Saldo Reprogramado",
                    "Custeio": s_reprog_cust, "Capital": s_reprog_cap},
                {"Descrição": "09 - Valor Creditado",
                    "Custeio": cred_cust, "Capital": cred_cap},
                {"Descrição": "10 - Recursos Próprios",
                    "Custeio": rec_prop_cust, "Capital": rec_prop_cap},
                {"Descrição": "11 - Rendimento de Aplicação",
                    "Custeio": rend_cust, "Capital": rend_cap},
                {"Descrição": "12 - Devolução de Recursos (-)",
                 "Custeio": devol_cust, "Capital": devol_cap},
                {"Descrição": "13 - VALOR TOTAL RECEITA",
                    "Custeio": total_rec_cust, "Capital": total_rec_cap},
                {"Descrição": "14 - Despesas Realizadas",
                    "Custeio": desp_cust, "Capital": desp_cap},
                {"Descrição": "15 - Saldo a Reprogramar",
                    "Custeio": saldo_final_cust, "Capital": saldo_final_cap},
            ])
            df_demo["Total"] = df_demo["Custeio"] + df_demo["Capital"]

            def highlight_demo_rows(row):
                if "13 - VALOR" in row['Descrição'] or "15 - Saldo" in row['Descrição']:
                    return ['background-color: #e0f2f1; color: black; font-weight: bold'] * len(row)
                return [''] * len(row)
            st.dataframe(df_demo.style.format({
                "Custeio": "R$ {:,.2f}", "Capital": "R$ {:,.2f}", "Total": "R$ {:,.2f}"
            }).apply(highlight_demo_rows, axis=1), use_container_width=True, height=350)

        with st.expander("Ver Resumo Geral de Todos os Programas"):
            dados_resumo = []
            col_saldo_ant = f"Saldo {ano_atual-1}"
            col_credito = f"Crédito {ano_atual}"
            col_rend = f"Rendimentos {ano_atual}"
            col_debito = f"Débitos {ano_atual}"
            col_saldo_final = f"Saldo 31.12.{ano_atual}"

            for prog in programas:
                saldo_anterior = get_saldo_anterior(
                    conta_atual, prog, 'Total', 1, ano_atual)
                movs_ano = [m for m in movs if m['programa']
                            == prog and m.get('ano') == ano_atual]
                credito_ano = sum(m['total_credito'] for m in movs_ano)
                rendimento_ano = sum(m['total_rendimento'] for m in movs_ano)
                debito_ano = sum(m['total_debito'] for m in movs_ano)
                saldo_final = saldo_anterior + credito_ano + rendimento_ano - debito_ano
                dados_resumo.append({
                    "Programas": prog, col_saldo_ant: saldo_anterior, col_credito: credito_ano,
                    col_rend: rendimento_ano, col_debito: debito_ano, col_saldo_final: saldo_final
                })

            if dados_resumo:
                df_resumo = pd.DataFrame(dados_resumo)
                linha_total = {
                    "Programas": "TOTAL GERAL", col_saldo_ant: df_resumo[col_saldo_ant].sum(),
                    col_credito: df_resumo[col_credito].sum(), col_rend: df_resumo[col_rend].sum(),
                    col_debito: df_resumo[col_debito].sum(), col_saldo_final: df_resumo[col_saldo_final].sum()
                }
                df_resumo = pd.concat(
                    [df_resumo, pd.DataFrame([linha_total])], ignore_index=True)

                def highlight_total_resumo(row):
                    return ['background-color: #ffd700; color: black; font-weight: bold'] * len(row) if row['Programas'] == 'TOTAL GERAL' else [''] * len(row)
                st.dataframe(df_resumo.style.format({
                    col_saldo_ant: "R$ {:,.2f}", col_credito: "R$ {:,.2f}", col_rend: "R$ {:,.2f}",
                    col_debito: "R$ {:,.2f}", col_saldo_final: "R$ {:,.2f}"
                }).apply(highlight_total_resumo, axis=1), use_container_width=True)

# === VISUALIZAÇÃO 2: MÓDULO EMPENHOS (GLOBAL) ===


def render_empenhos_global_view():
    st.subheader("📜 Controle de Empenhos e Ordens de Pagamento (Global)")

    # Inicializa estado da tela se não existir
    if 'empenho_mode' not in st.session_state:
        st.session_state['empenho_mode'] = 'list'  # 'list' ou 'form'

    if 'empenho_em_edicao' not in st.session_state:
        st.session_state['empenho_em_edicao'] = None

    # --- TELA 1: LISTAGEM ---
    if st.session_state['empenho_mode'] == 'list':
        # 1. Gerenciamento de Programas
        with st.expander("⚙️ Cadastrar/Gerenciar Programas"):
            c_p1, c_p2 = st.columns([3, 1])
            novo_prog_global = c_p1.text_input(
                "Novo Programa", key="new_prog_global")
            if c_p2.button("Cadastrar", key="btn_add_prog_global"):
                if novo_prog_global and novo_prog_global not in st.session_state['global_programs']:
                    st.session_state['global_programs'].append(
                        novo_prog_global)
                    save_global_programs_to_firebase(
                        st.session_state['db_conn'], st.session_state['global_programs'])
                    st.success("Programa cadastrado!")
                    st.rerun()
                elif novo_prog_global:
                    st.warning("Programa já existe.")

            if st.session_state['global_programs']:
                st.write("Programas cadastrados: " +
                         ", ".join(st.session_state['global_programs']))
            else:
                st.info("Nenhum programa cadastrado para empenhos.")

        st.divider()

        # Botão de Novo Registro
        col_new, _ = st.columns([1, 4])
        if col_new.button("➕ Novo Empenho", type="primary"):
            st.session_state['empenho_em_edicao'] = None
            st.session_state['empenho_mode'] = 'form'
            st.rerun()

        # Filtros
        anos_disp = sorted(st.session_state.get(
            'available_years', [datetime.now().year]))
        str_anos = [str(a) for a in anos_disp]
        ano_filtro = st.radio("Filtrar por Ano:", str_anos,
                              horizontal=True, index=len(str_anos)-1)

        lista_programas = st.session_state['global_programs']
        if not lista_programas:
            lista_programas = ["Sem cadastro"]
        filtro_prog_emp = st.selectbox("Filtrar por Programa", [
                                       "Todos"] + lista_programas, key="filt_gemp")

        # Dados
        todos_empenhos = st.session_state['empenhos_global']
        empenhos_ano = []
        for emp in todos_empenhos:
            try:
                dt = datetime.strptime(emp.get('data_empenho', ''), "%Y-%m-%d")
                if str(dt.year) == ano_filtro:
                    empenhos_ano.append(emp)
            except:
                pass

        # Ordenação
        empenhos_ano.sort(key=lambda x: x.get(
            'data_empenho', ''), reverse=True)

        lista_final = empenhos_ano
        if filtro_prog_emp != "Todos":
            lista_final = [
                e for e in empenhos_ano if e['programa'] == filtro_prog_emp]

        st.markdown(f"**Registros Encontrados: {len(lista_final)}**")

        if lista_final:
            # Cabeçalho Customizado
            c1, c2, c3, c4, c5, c6 = st.columns([1.2, 2, 1, 1.2, 1.2, 1])
            c1.markdown("<div class='row-header'>Data</div>",
                        unsafe_allow_html=True)
            c2.markdown("<div class='row-header'>Programa</div>",
                        unsafe_allow_html=True)
            c3.markdown("<div class='row-header'>Nº Emp.</div>",
                        unsafe_allow_html=True)
            c4.markdown("<div class='row-header'>Valor</div>",
                        unsafe_allow_html=True)
            c5.markdown("<div class='row-header'>Status</div>",
                        unsafe_allow_html=True)
            c6.markdown("<div class='row-header'>Ação</div>",
                        unsafe_allow_html=True)

            for item in lista_final:
                with st.container():
                    col1, col2, col3, col4, col5, col6 = st.columns(
                        [1.2, 2, 1, 1.2, 1.2, 1])

                    try:
                        d_show = datetime.strptime(
                            item.get('data_empenho', ''), "%Y-%m-%d").strftime("%d/%m/%Y")
                    except:
                        d_show = "-"

                    val_show = format_currency(float(item.get('valor', 0)))

                    col1.text(d_show)
                    col2.text(item.get('programa', '-'))
                    col3.text(item.get('numero_empenho', '-'))
                    col4.text(val_show)
                    col5.text(item.get('status', '-'))

                    if col6.button("✏️ Editar", key=f"btn_edit_{item['id']}"):
                        st.session_state['empenho_em_edicao'] = item
                        st.session_state['empenho_mode'] = 'form'
                        st.rerun()

                    st.markdown(
                        "<div style='border-bottom: 1px solid #eee; margin-bottom: 5px;'></div>", unsafe_allow_html=True)

            # Totais
            total_val = sum([float(i.get('valor', 0)) for i in lista_final])
            st.metric("Total (Filtro)", format_currency(total_val))
        else:
            st.info("Nenhum registro encontrado com os filtros atuais.")

    # --- TELA 2: FORMULÁRIO (NOVO / EDIÇÃO) ---
    elif st.session_state['empenho_mode'] == 'form':
        # Botão Voltar no topo
        if st.button("⬅️ Voltar para a Lista", key="btn_back_top"):
            st.session_state['empenho_mode'] = 'list'
            st.rerun()

        st.divider()

        # Preparação de Dados
        dados_edicao = st.session_state['empenho_em_edicao']
        is_edit_mode = dados_edicao is not None

        file_info = None
        if is_edit_mode and dados_edicao.get('has_file'):
            with st.spinner("Carregando anexo..."):
                file_info = get_file_from_firebase(
                    st.session_state['db_conn'], dados_edicao.get('id'))

        # Helper datas
        def safe_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except:
                return None

        # Valores Iniciais
        val_prog = dados_edicao.get('programa') if is_edit_mode else None
        val_num = dados_edicao.get('numero_empenho', "")
        val_data = safe_date(dados_edicao.get(
            'data_empenho')) if is_edit_mode else None
        val_ob = dados_edicao.get('ordem_bancaria', "")
        val_data_ob = safe_date(dados_edicao.get(
            'data_ob')) if is_edit_mode else None
        val_valor = float(dados_edicao.get('valor', 0.0))
        val_data_nf = safe_date(dados_edicao.get('data_nota_fiscal', dados_edicao.get(
            'data_utilizacao', ''))) if is_edit_mode else None
        val_status = dados_edicao.get('status', "PENDENTE")
        val_obs = dados_edicao.get('observacao', "")
        val_itens = dados_edicao.get('itens', "")

        lista_programas = st.session_state['global_programs']
        if not lista_programas:
            lista_programas = ["Sem cadastro"]
        prog_index = lista_programas.index(val_prog) if (
            is_edit_mode and val_prog in lista_programas) else 0

        # Formulário Visual
        titulo = "✏️ Editando Empenho" if is_edit_mode else "➕ Novo Empenho"
        st.markdown(f"### {titulo}")

        with st.container(border=True):
            ce1, ce2, ce3 = st.columns(3)
            e_prog = ce1.selectbox(
                "Programa", options=lista_programas, index=prog_index, key="form_prog")
            e_num = ce2.text_input("Nº Empenho", value=val_num, key="form_num")
            e_data = ce3.date_input(
                "Data do Empenho", value=val_data, format="DD/MM/YYYY", key="form_data")

            ce4, ce5, ce6 = st.columns(3)
            e_ob = ce4.text_input("Ordem Bancária (OB)",
                                  value=val_ob, key="form_ob")
            e_data_ob = ce5.date_input(
                "Data da OB", value=val_data_ob, format="DD/MM/YYYY", key="form_data_ob")
            e_valor = ce6.number_input(
                "Valor (R$)", value=val_valor, min_value=0.0, step=0.01, format="%.2f", key="form_valor")

            ce7, ce8, ce9 = st.columns(3)
            status_opts = ["EXECUTADO", "PENDENTE", "CANCELADO"]
            e_status = ce7.selectbox("Status", status_opts, index=status_opts.index(
                val_status) if val_status in status_opts else 1, key="form_status")

            e_data_nf = None
            if e_status == "EXECUTADO":
                e_data_nf = ce8.date_input(
                    "Data Nota Fiscal", value=val_data_nf, format="DD/MM/YYYY", key="form_data_nf")
            else:
                ce8.write("---")

            e_obs = ce9.text_input("Observação", value=val_obs, key="form_obs")
            e_itens = st.text_area(
                "Itens Comprados / Descrição", value=val_itens, height=100, key="form_itens")

            # Arquivos
            st.markdown("#### 📎 Anexo (PDF)")

            if is_edit_mode and file_info:
                st.markdown(f"""
                    <div class="download-box">
                        <b>Arquivo atual:</b> {file_info.get('file_name', 'arquivo.pdf')}
                    </div>
                """, unsafe_allow_html=True)

                # Download Button Logic
                b64_data = file_info.get('file_data')
                try:
                    bin_data = base64.b64decode(b64_data)
                    st.download_button(
                        label="⬇️ Baixar Arquivo Atual",
                        data=bin_data,
                        file_name=file_info.get('file_name', 'arquivo.pdf'),
                        mime='application/pdf'
                    )
                except:
                    st.error("Erro ao preparar download.")

                e_file = st.file_uploader("Substituir arquivo (Opcional)", type=[
                                          "pdf"], key="form_file")
            else:
                e_file = st.file_uploader("Fazer upload de PDF (Máx 2MB)", type=[
                                          "pdf"], key="form_file")

            st.markdown("---")

            # Botões de Ação
            c_act1, c_act2, c_act3 = st.columns([1, 1, 4])

            # Helper Salvar
            def run_save():
                if not e_data:
                    st.error("⚠️ Data do Empenho é obrigatória!")
                    return
                if e_status == "EXECUTADO" and not e_data_nf:
                    st.error(
                        "⚠️ Data Nota Fiscal é obrigatória para status Executado!")
                    return

                str_d_emp = e_data.strftime("%Y-%m-%d")
                str_d_ob = e_data_ob.strftime("%Y-%m-%d") if e_data_ob else ""
                str_d_nf = e_data_nf.strftime("%Y-%m-%d") if e_data_nf else ""

                payload = {
                    "programa": e_prog, "numero_empenho": e_num, "data_empenho": str_d_emp,
                    "ordem_bancaria": e_ob, "data_ob": str_d_ob, "valor": e_valor,
                    "data_nota_fiscal": str_d_nf, "status": e_status, "itens": e_itens, "observacao": e_obs
                }

                target_id = dados_edicao.get('id') if is_edit_mode else str(
                    datetime.now().timestamp())

                # File Logic
                if e_file:
                    ok = save_file_to_firebase(
                        st.session_state['db_conn'], target_id, e_file)
                    if ok:
                        payload['has_file'] = True
                        payload['file_name'] = e_file.name
                elif is_edit_mode and dados_edicao.get('has_file'):
                    payload['has_file'] = True
                    payload['file_name'] = dados_edicao.get('file_name')

                # Update State list
                if is_edit_mode:
                    idx = -1
                    for i, e in enumerate(st.session_state['empenhos_global']):
                        if e.get('id') == target_id:
                            idx = i
                            break
                    if idx != -1:
                        st.session_state['empenhos_global'][idx].update(
                            payload)
                else:
                    payload['id'] = target_id
                    st.session_state['empenhos_global'].append(payload)

                save_empenhos_to_firebase(
                    st.session_state['db_conn'], st.session_state['empenhos_global'])
                st.success("Salvo com sucesso!")
                st.session_state['empenho_mode'] = 'list'  # Voltar para lista
                st.rerun()

            if c_act1.button("💾 Salvar", type="primary"):
                run_save()

            if c_act2.button("❌ Cancelar"):
                st.session_state['empenho_mode'] = 'list'
                st.rerun()

            if is_edit_mode:
                with c_act3:
                    with st.popover("🗑️ Excluir"):
                        st.write("Tem certeza?")
                        if st.button("Sim, excluir permanentemente"):
                            t_id = dados_edicao.get('id')
                            idx = -1
                            for i, e in enumerate(st.session_state['empenhos_global']):
                                if e.get('id') == t_id:
                                    idx = i
                                    break
                            if idx != -1:
                                st.session_state['empenhos_global'].pop(idx)
                                delete_file_from_firebase(
                                    st.session_state['db_conn'], t_id)
                                save_empenhos_to_firebase(
                                    st.session_state['db_conn'], st.session_state['empenhos_global'])
                                st.session_state['empenho_mode'] = 'list'
                                st.rerun()

# === VISUALIZAÇÃO 3: RESUMO CONSOLIDADO (NOVO) ===


def render_resumo_consolidado_view():
    st.subheader("📈 Resumo Geral Consolidado (Todas as Contas)")

    anos_disp = sorted(st.session_state.get(
        'available_years', [datetime.now().year]))
    str_anos = [str(a) for a in anos_disp]

    # Filtro de Ano
    col_filtro, _ = st.columns([1, 3])
    ano_selecionado = col_filtro.selectbox(
        "Selecione o Ano:", str_anos, index=len(str_anos)-1)
    ano_int = int(ano_selecionado)

    # 1. Calcular Totais
    total_recebido = 0.0
    total_gasto = 0.0
    total_saldo_atual = 0.0

    # Lista para a Tabela Detalhada
    lista_detalhada = []

    # Itera sobre todas as contas
    for nome_conta, dados_conta in st.session_state['accounts'].items():
        movs = dados_conta.get('movimentacoes', [])
        progs = dados_conta.get('programas', [])

        # Filtra movimentos do ano
        movs_ano = [m for m in movs if m.get('ano') == ano_int]

        # Calcula Totais da Conta
        saldo_inicial_conta = 0.0
        creditos_conta = sum(m['total_credito'] for m in movs_ano)
        rendimentos_conta = sum(m['total_rendimento'] for m in movs_ano)
        debitos_conta = sum(m['total_debito'] for m in movs_ano)

        # Para saldo inicial, somamos o saldo de todos os programas
        for p in progs:
            saldo_inicial_conta += get_saldo_anterior(
                nome_conta, p, 'Total', 1, ano_int)

        receita_total_conta = saldo_inicial_conta + creditos_conta + rendimentos_conta
        saldo_final_conta = receita_total_conta - debitos_conta

        # Acumula nos totais gerais
        # Entradas puras no ano
        total_recebido += (creditos_conta + rendimentos_conta)
        total_gasto += debitos_conta
        total_saldo_atual += saldo_final_conta

        lista_detalhada.append({
            "Conta": nome_conta,
            "Saldo Anterior": saldo_inicial_conta,
            "Créditos": creditos_conta,
            "Rendimentos": rendimentos_conta,
            "Débitos": debitos_conta,
            "Saldo Final": saldo_final_conta
        })

    # 2. Exibir Cartões de Métricas
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Entradas (Créd + Rend)",
                format_currency(total_recebido), delta_color="normal")
    col2.metric("Total Saídas (Débitos)", format_currency(
        total_gasto), delta_color="inverse")  # Vermelho se subir
    col3.metric("Saldo Geral Acumulado", format_currency(total_saldo_atual))

    st.divider()

    # 3. Tabela Detalhada por Conta
    st.markdown(f"#### Detalhamento por Conta - {ano_int}")
    if lista_detalhada:
        df_resumo = pd.DataFrame(lista_detalhada)

        # Adiciona Linha de Total
        linha_total = {
            "Conta": "TOTAL GERAL",
            "Saldo Anterior": df_resumo["Saldo Anterior"].sum(),
            "Créditos": df_resumo["Créditos"].sum(),
            "Rendimentos": df_resumo["Rendimentos"].sum(),
            "Débitos": df_resumo["Débitos"].sum(),
            "Saldo Final": df_resumo["Saldo Final"].sum()
        }
        df_resumo = pd.concat(
            [df_resumo, pd.DataFrame([linha_total])], ignore_index=True)

        def highlight_total(row):
            return ['background-color: #ffd700; color: black; font-weight: bold'] * len(row) if row['Conta'] == 'TOTAL GERAL' else [''] * len(row)

        st.dataframe(
            df_resumo.style.format({
                "Saldo Anterior": "R$ {:,.2f}",
                "Créditos": "R$ {:,.2f}",
                "Rendimentos": "R$ {:,.2f}",
                "Débitos": "R$ {:,.2f}",
                "Saldo Final": "R$ {:,.2f}"
            }).apply(highlight_total, axis=1),
            use_container_width=True,
            height=400
        )
    else:
        st.info("Nenhuma conta encontrada.")


def main():
    init_session_state()
    modulo_selecionado, conta_selecionada = sidebar_config()
    st.title(f"📊 {modulo_selecionado}")

    if modulo_selecionado == "🏦 Movimentação Financeira":
        if not conta_selecionada:
            st.info(
                "👈 Cadastre uma conta na barra lateral para começar a usar o financeiro.")
            return

        nome = conta_selecionada
        st.header(f"Conta: {nome}")

        with st.expander("⚙️ Gerenciar Programas da Conta"):
            c1, c2 = st.columns([3, 1])
            novo = c1.text_input("Novo Programa", key=f"np_{nome}")
            if c2.button("Adicionar", key=f"b_{nome}"):
                if novo and novo not in st.session_state['accounts'][nome]['programas']:
                    st.session_state['accounts'][nome]['programas'].append(
                        novo)
                    if 'saldos_iniciais' not in st.session_state['accounts'][nome]:
                        st.session_state['accounts'][nome]['saldos_iniciais'] = {
                        }
                    st.session_state['accounts'][nome]['saldos_iniciais'][novo] = {
                        'Capital': 0.0, 'Custeio': 0.0}
                    save_account_to_firebase(
                        st.session_state['db_conn'], nome, st.session_state['accounts'][nome])
                    st.rerun()

            st.divider()
            st.markdown("**Programas Ativos:**")
            progs = st.session_state['accounts'][nome].get('programas', [])
            if progs:
                for p in progs:
                    col_p1, col_p2 = st.columns([4, 1])
                    col_p1.text(f"📌 {p}")
                    if col_p2.button("🗑️", key=f"del_prog_{nome}_{p}", help=f"Excluir programa {p}"):
                        st.session_state['accounts'][nome]['programas'].remove(
                            p)
                        if 'saldos_iniciais' in st.session_state['accounts'][nome]:
                            st.session_state['accounts'][nome]['saldos_iniciais'].pop(
                                p, None)
                        save_account_to_firebase(
                            st.session_state['db_conn'], nome, st.session_state['accounts'][nome])
                        st.success(f"Programa '{p}' removido!")
                        st.rerun()
                st.write("---")
                st.write("Saldos Iniciais (Abertura de Conta):")
                for p in progs:
                    si = st.session_state['accounts'][nome].setdefault(
                        'saldos_iniciais', {}).setdefault(p, {'Capital': 0.0, 'Custeio': 0.0})
                    k = f"{nome}_{p}"
                    cols = st.columns([2, 1, 1, 1])
                    cols[0].write(f"📂 {p}")
                    n_cap = cols[1].number_input(
                        "Saldo Inicial Capital", value=si['Capital'], key=f"sic_{k}")
                    n_cus = cols[2].number_input(
                        "Saldo Inicial Custeio", value=si['Custeio'], key=f"sis_{k}")
                    if cols[3].button("Salvar", key=f"bts_{k}"):
                        si['Capital'] = n_cap
                        si['Custeio'] = n_cus
                        save_account_to_firebase(
                            st.session_state['db_conn'], nome, st.session_state['accounts'][nome])
                        st.rerun()

        if st.session_state['accounts'][nome]['programas']:
            anos = sorted(st.session_state.get(
                'available_years', [datetime.now().year]))
            for aba_ano, ano in zip(st.tabs([str(a) for a in anos]), anos):
                with aba_ano:
                    render_financeiro_view(
                        nome, ano, st.session_state['accounts'][nome]['programas'])
        else:
            st.warning("Cadastre programas acima para começar.")

    elif modulo_selecionado == "📜 Controle de Empenhos":
        render_empenhos_global_view()

    elif modulo_selecionado == "📈 Resumo Consolidado":
        render_resumo_consolidado_view()


if __name__ == "__main__":
    main()
