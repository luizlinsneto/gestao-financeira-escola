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
st.markdown("""
    <style>
    .stNumberInput input { text-align: right; }
    .big-font { font-size: 18px !important; font-weight: bold; }
    div[data-testid="stMetricValue"] { font-size: 24px; }
    </style>
    """, unsafe_allow_html=True)

# --- CONEXÃO COM FIREBASE ---
@st.cache_resource
def init_firebase():
    """Inicializa a conexão com Firebase apenas uma vez e mantém em cache."""
    if not firebase_admin._apps:
        cred = None
        
        # 1. TENTATIVA LOCAL
        if os.path.exists("firebase_key.json"):
            try:
                cred = credentials.Certificate("firebase_key.json")
            except Exception as e:
                st.error(f"Erro no arquivo json: {e}")
                return None
        
        # 2. TENTATIVA NUVEM
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

def load_data_from_firebase(db):
    if db is None: return {}
    try:
        accounts_ref = db.collection('pdde_contas')
        docs = accounts_ref.stream()
        dados_carregados = {}
        for doc in docs:
            dados_carregados[doc.id] = doc.to_dict()
        return dados_carregados
    except Exception as e:
        st.error(f"Erro ao ler banco: {e}")
        return {}

def save_account_to_firebase(db, account_name, account_data):
    if db is None: return
    try:
        db.collection('pdde_contas').document(account_name).set(account_data)
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

# --- FUNÇÕES AUXILIARES ---

def format_currency(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def init_session_state():
    # Inicializa conexão
    db = init_firebase()
    st.session_state['db_conn'] = db
    
    # OTIMIZAÇÃO: Só carrega do banco se ainda não tiver carregado
    if 'accounts' not in st.session_state:
        if db:
            with st.spinner('Conectando ao banco de dados...'):
                st.session_state['accounts'] = load_data_from_firebase(db)
        else:
            st.session_state['accounts'] = {}
        
    if 'available_years' not in st.session_state:
        current_year = datetime.now().year
        anos_encontrados = set([current_year])
        for conta in st.session_state['accounts'].values():
            for mov in conta.get('movimentacoes', []):
                anos_encontrados.add(mov.get('ano', current_year))
        st.session_state['available_years'] = sorted(list(anos_encontrados))

def get_saldo_anterior(account_name, programa, tipo_recurso, mes_alvo, ano_alvo):
    conta_data = st.session_state['accounts'][account_name]
    movs = conta_data.get('movimentacoes', []) 
    
    saldo = 0.0
    saldos_iniciais = conta_data.get('saldos_iniciais', {})
    
    if programa in saldos_iniciais:
        val = saldos_iniciais[programa].get(tipo_recurso, 0.0) if tipo_recurso != 'Total' else \
              saldos_iniciais[programa].get('Capital', 0.0) + saldos_iniciais[programa].get('Custeio', 0.0)
        saldo += val

    for mov in movs:
        mov_ano = mov.get('ano', datetime.now().year)
        mov_mes = mov['mes_num']
        
        eh_passado = (mov_ano < ano_alvo) or (mov_ano == ano_alvo and mov_mes < mes_alvo)
        
        if mov['programa'] == programa and eh_passado:
            if tipo_recurso == 'Capital':
                saldo += (mov['credito_capital'] + mov['rendimento_capital'] - mov['debito_capital'])
            elif tipo_recurso == 'Custeio':
                saldo += (mov['credito_custeio'] + mov['rendimento_custeio'] - mov['debito_custeio'])
            elif tipo_recurso == 'Total':
                saldo += (mov['total_credito'] + mov['total_rendimento'] - mov['total_debito'])
                
    return saldo

# --- BARRA LATERAL ---
def sidebar_config():
    st.sidebar.header("⚙️ Configurações Gerais")
    
    if st.session_state['db_conn'] is None:
        st.sidebar.error("⚠️ Sem conexão com Banco de Dados")
        st.sidebar.info("Verifique o arquivo firebase_key.json")
    
    with st.sidebar.expander("1. Cadastrar Nova Conta"):
        nova_conta = st.text_input("Número da Conta / Nome", placeholder="Ex: 27.922-6")
        if st.button("Adicionar Conta"):
            if nova_conta and nova_conta not in st.session_state['accounts']:
                nova_estrutura = {'programas': [], 'movimentacoes': [], 'saldos_iniciais': {}}
                st.session_state['accounts'][nova_conta] = nova_estrutura
                save_account_to_firebase(st.session_state['db_conn'], nova_conta, nova_estrutura)
                st.success(f"Conta {nova_conta} criada!")
                st.rerun()
            elif nova_conta in st.session_state['accounts']:
                st.warning("Conta já existe.")

    with st.sidebar.expander("2. Gerenciar Exercícios (Anos)"):
        novo_ano = st.number_input("Adicionar Ano", min_value=2000, max_value=2050, value=datetime.now().year + 1, step=1)
        if st.button("Criar Novo Exercício"):
            if novo_ano not in st.session_state['available_years']:
                st.session_state['available_years'].append(novo_ano)
                st.session_state['available_years'].sort()
                st.success(f"Exercício de {novo_ano} adicionado!")
                st.rerun()
            else:
                st.warning("Este ano já existe.")

# --- LÓGICA DE RENDIMENTO ---
def calcular_rateio_rendimento(conta, mes_num, ano, rendimento_total_banco, dados_entrada):
    saldos_base = {}
    total_saldo_conta = 0.0
    
    for prog, valores in dados_entrada.items():
        saldo_ant_cap = get_saldo_anterior(conta, prog, 'Capital', mes_num, ano)
        saldo_ant_cus = get_saldo_anterior(conta, prog, 'Custeio', mes_num, ano)
        
        base_cap = max(0, saldo_ant_cap + valores['cred_cap'] - valores['deb_cap'])
        base_cus = max(0, saldo_ant_cus + valores['cred_cus'] - valores['deb_cus'])
        
        saldos_base[prog] = { 'Capital': base_cap, 'Custeio': base_cus }
        total_saldo_conta += (base_cap + base_cus)
    
    resultados = []
    
    for prog, valores in dados_entrada.items():
        base_prog = saldos_base[prog]
        
        if total_saldo_conta > 0:
            fator_cap = base_prog['Capital'] / total_saldo_conta
            fator_cus = base_prog['Custeio'] / total_saldo_conta
        else:
            fator_cap = 0
            fator_cus = 0
            
        rend_cap = rendimento_total_banco * fator_cap
        rend_cus = rendimento_total_banco * fator_cus
        
        resultados.append({
            'programa': prog,
            'mes_num': mes_num,
            'ano': ano,
            'credito_capital': valores['cred_cap'],
            'credito_custeio': valores['cred_cus'],
            'debito_capital': valores['deb_cap'],
            'debito_custeio': valores['deb_cus'],
            'rendimento_capital': rend_cap,
            'rendimento_custeio': rend_cus,
            'total_credito': valores['cred_cap'] + valores['cred_cus'],
            'total_debito': valores['deb_cap'] + valores['deb_cus'],
            'total_rendimento': rend_cap + rend_cus
        })
        
    return resultados

# --- VISUALIZAÇÃO ---
def render_year_view(conta_atual, ano_atual, programas):
    tab_lanc, tab_rel, tab_resumo = st.tabs(["📝 Lançamentos", "📑 Extrato Mensal", "📊 Resumo Anual"])

    # === ABA 1: LANÇAMENTOS ===
    with tab_lanc:
        col_mes, col_rend = st.columns([1, 2])
        meses = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 
                 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
        
        with col_mes:
            mes_selecionado = st.selectbox("Mês", options=list(meses.keys()), format_func=lambda x: meses[x], key=f"sel_mes_{conta_atual}_{ano_atual}")
        
        movs = st.session_state['accounts'][conta_atual].get('movimentacoes', [])
        registros_existentes = [m for m in movs if m['mes_num'] == mes_selecionado and m.get('ano', datetime.now().year) == ano_atual]
        
        val_rendimento_inicial = 0.0
        if registros_existentes:
            val_rendimento_inicial = sum([m['total_rendimento'] for m in registros_existentes])
            st.info(f"✏️ Editando dados de {meses[mes_selecionado]}.")

        with col_rend:
            rendimento_total = st.number_input(
                "💰 Rendimento/Ajuste (Total Extrato)", 
                value=float(val_rendimento_inicial), step=0.01, format="%.2f", 
                key=f"rend_tot_{conta_atual}_{ano_atual}_{mes_selecionado}"
            )

        st.divider()
        dados_entrada = {}
        for prog in programas:
            prog_data = next((m for m in registros_existentes if m['programa'] == prog), None)
            
            v_cc = float(prog_data['credito_capital']) if prog_data else 0.0
            v_crc = float(prog_data['credito_custeio']) if prog_data else 0.0
            v_dc = float(prog_data['debito_capital']) if prog_data else 0.0
            v_dec = float(prog_data['debito_custeio']) if prog_data else 0.0

            with st.expander(f"Movimento: {prog}", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                
                saldo_ant_cap = get_saldo_anterior(conta_atual, prog, 'Capital', mes_selecionado, ano_atual)
                saldo_ant_cus = get_saldo_anterior(conta_atual, prog, 'Custeio', mes_selecionado, ano_atual)
                
                st.markdown(f"**Saldo Ant.:** Cap: {format_currency(saldo_ant_cap)} | Cust: {format_currency(saldo_ant_cus)}")
                
                k_suf = f"{conta_atual}_{prog}_{ano_atual}_{mes_selecionado}"
                
                cred_cap = c1.number_input(f"Créd. Capital", min_value=0.0, value=v_cc, key=f"cc_{k_suf}")
                cred_cus = c2.number_input(f"Créd. Custeio", min_value=0.0, value=v_crc, key=f"crc_{k_suf}")
                deb_cap = c3.number_input(f"Déb. Capital", min_value=0.0, value=v_dc, key=f"dc_{k_suf}")
                deb_cus = c4.number_input(f"Déb. Custeio", min_value=0.0, value=v_dec, key=f"dec_{k_suf}")
                
                dados_entrada[prog] = {'cred_cap': cred_cap, 'cred_cus': cred_cus, 'deb_cap': deb_cap, 'deb_cus': deb_cus}

        if st.button(f"💾 Salvar Lançamento {meses[mes_selecionado]}/{ano_atual}", type="primary", key=f"btn_save_{conta_atual}_{ano_atual}_{mes_selecionado}"):
            novos_registros = calcular_rateio_rendimento(conta_atual, mes_selecionado, ano_atual, rendimento_total, dados_entrada)
            
            lista_atual = st.session_state['accounts'][conta_atual].get('movimentacoes', [])
            lista_limpa = [m for m in lista_atual if not (m['mes_num'] == mes_selecionado and m.get('ano', datetime.now().year) == ano_atual)]
            lista_limpa.extend(novos_registros)
            
            st.session_state['accounts'][conta_atual]['movimentacoes'] = lista_limpa
            save_account_to_firebase(st.session_state['db_conn'], conta_atual, st.session_state['accounts'][conta_atual])
            
            st.success("Dados salvos com sucesso!")
            st.rerun()

    # === ABA 2: EXTRATO MENSAL ===
    with tab_rel:
        st.subheader(f"Extrato Mensal Detalhado - {ano_atual}")
        filtro_prog = st.selectbox("Filtrar Programa", ["Todos"] + programas, key=f"filt_prog_{conta_atual}_{ano_atual}")
        
        movs = st.session_state['accounts'][conta_atual].get('movimentacoes', [])
        programas_para_listar = programas if filtro_prog == "Todos" else [filtro_prog]
        
        df_final = pd.DataFrame()

        for p in programas_para_listar:
            dados_tabela = []
            saldo_acumulado_cap = get_saldo_anterior(conta_atual, p, 'Capital', 1, ano_atual)
            saldo_acumulado_cus = get_saldo_anterior(conta_atual, p, 'Custeio', 1, ano_atual)
            
            movs_prog_ano = [m for m in movs if m['programa'] == p and m.get('ano', datetime.now().year) == ano_atual]
            movs_prog_ano.sort(key=lambda x: x['mes_num'])
            
            for m in movs_prog_ano:
                saldo_acumulado_cap += (m['credito_capital'] + m['rendimento_capital'] - m['debito_capital'])
                saldo_acumulado_cus += (m['credito_custeio'] + m['rendimento_custeio'] - m['debito_custeio'])
                saldo_total = saldo_acumulado_cap + saldo_acumulado_cus
                
                dados_tabela.append({
                    "Programa": p, "Mês": meses[m['mes_num']],
                    "Crédito": m['total_credito'], "Rend. Cap.": m['rendimento_capital'],
                    "Rend. Cust.": m['rendimento_custeio'], "Rend. Total": m['total_rendimento'],
                    "Débito": m['total_debito'], "S. Custeio": saldo_acumulado_cus,
                    "S. Capital": saldo_acumulado_cap, "S. Total": saldo_total
                })
            
            if dados_tabela:
                df_prog = pd.DataFrame(dados_tabela)
                # Totais
                linha_total = pd.DataFrame([{
                    "Programa": "TOTAL", "Mês": "---",
                    "Crédito": df_prog["Crédito"].sum(),
                    "Rend. Cap.": df_prog["Rend. Cap."].sum(),
                    "Rend. Cust.": df_prog["Rend. Cust."].sum(),
                    "Rend. Total": df_prog["Rend. Total"].sum(),
                    "Débito": df_prog["Débito"].sum(),
                    "S. Custeio": df_prog["S. Custeio"].iloc[-1],
                    "S. Capital": df_prog["S. Capital"].iloc[-1],
                    "S. Total": df_prog["S. Total"].iloc[-1]
                }])
                df_final = pd.concat([df_final, df_prog, linha_total], ignore_index=True)

        if not df_final.empty:
            def highlight_total(row):
                return ['background-color: #ffd700; color: black; font-weight: bold'] * len(row) if row['Programa'] == 'TOTAL' else [''] * len(row)

            st.dataframe(
                df_final.style.format({
                    "Crédito": "R$ {:,.2f}", "Rend. Cap.": "R$ {:,.2f}", "Rend. Cust.": "R$ {:,.2f}",
                    "Rend. Total": "R$ {:,.2f}", "Débito": "R$ {:,.2f}", "S. Custeio": "R$ {:,.2f}",
                    "S. Capital": "R$ {:,.2f}", "S. Total": "R$ {:,.2f}",
                }).apply(highlight_total, axis=1),
                use_container_width=True, height=500
            )
        else:
            st.info(f"Nenhuma movimentação em {ano_atual}.")
    
    # === ABA 3: RESUMO ANUAL (IGUAL A IMAGEM) ===
    with tab_resumo:
        st.subheader(f"Resumo Geral das Contas - Exercício {ano_atual}")
        
        dados_resumo = []
        movs = st.session_state['accounts'][conta_atual].get('movimentacoes', [])
        
        # Nomes das colunas dinâmicas
        col_saldo_ant = f"Saldo {ano_atual-1}"
        col_credito = f"Crédito {ano_atual}"
        col_rend = f"Rendimentos {ano_atual}"
        col_debito = f"Débitos {ano_atual}"
        col_saldo_final = f"Saldo 31.12.{ano_atual}"

        for prog in programas:
            # 1. Calcula saldo acumulado até o final do ano anterior
            saldo_anterior = get_saldo_anterior(conta_atual, prog, 'Total', 1, ano_atual)
            
            # 2. Filtra movimentações APENAS do ano atual
            movs_ano = [m for m in movs if m['programa'] == prog and m.get('ano') == ano_atual]
            
            # 3. Somas do ano
            credito_ano = sum(m['total_credito'] for m in movs_ano)
            rendimento_ano = sum(m['total_rendimento'] for m in movs_ano)
            debito_ano = sum(m['total_debito'] for m in movs_ano)
            
            # 4. Cálculo final: Saldo Ant + Entradas - Saídas
            saldo_final = saldo_anterior + credito_ano + rendimento_ano - debito_ano
            
            dados_resumo.append({
                "Programas": prog,
                col_saldo_ant: saldo_anterior,
                col_credito: credito_ano,
                col_rend: rendimento_ano,
                col_debito: debito_ano,
                col_saldo_final: saldo_final
            })
            
        if dados_resumo:
            df_resumo = pd.DataFrame(dados_resumo)
            
            # Linha de TOTAL GERAL
            linha_total = {
                "Programas": "TOTAL GERAL",
                col_saldo_ant: df_resumo[col_saldo_ant].sum(),
                col_credito: df_resumo[col_credito].sum(),
                col_rend: df_resumo[col_rend].sum(),
                col_debito: df_resumo[col_debito].sum(),
                col_saldo_final: df_resumo[col_saldo_final].sum()
            }
            
            df_resumo = pd.concat([df_resumo, pd.DataFrame([linha_total])], ignore_index=True)
            
            # Estilização igual à imagem (Total destacado)
            def highlight_total_resumo(row):
                if row['Programas'] == 'TOTAL GERAL':
                    # Fundo amarelo (ou vermelho se negativo) para o total
                    return ['background-color: #ffd700; color: black; font-weight: bold'] * len(row)
                return [''] * len(row)

            st.dataframe(
                df_resumo.style.format({
                    col_saldo_ant: "R$ {:,.2f}",
                    col_credito: "R$ {:,.2f}",
                    col_rend: "R$ {:,.2f}",
                    col_debito: "R$ {:,.2f}",
                    col_saldo_final: "R$ {:,.2f}"
                }).apply(highlight_total_resumo, axis=1),
                use_container_width=True,
                height=500
            )
        else:
            st.info("Sem dados para gerar resumo.")

def main():
    init_session_state()
    sidebar_config()
    st.title("📊 Controle Financeiro - PDDE")
    
    contas = list(st.session_state['accounts'].keys())
    if not contas:
        st.info("👈 Cadastre uma conta na barra lateral.")
        return

    for aba, nome in zip(st.tabs(contas), contas):
        with aba:
            st.header(f"Conta: {nome}")
            with st.expander("⚙️ Gerenciar Programas"):
                c1, c2 = st.columns([3, 1])
                novo = c1.text_input("Novo Programa", key=f"np_{nome}")
                if c2.button("Adicionar", key=f"b_{nome}"):
                    if novo and novo not in st.session_state['accounts'][nome]['programas']:
                        st.session_state['accounts'][nome]['programas'].append(novo)
                        if 'saldos_iniciais' not in st.session_state['accounts'][nome]:
                            st.session_state['accounts'][nome]['saldos_iniciais'] = {}
                        st.session_state['accounts'][nome]['saldos_iniciais'][novo] = {'Capital': 0.0, 'Custeio': 0.0}
                        save_account_to_firebase(st.session_state['db_conn'], nome, st.session_state['accounts'][nome])
                        st.rerun()
                
                # Config Saldos Iniciais
                progs = st.session_state['accounts'][nome].get('programas', [])
                if progs:
                    st.write("---")
                    st.write("Saldos Iniciais:")
                    for p in progs:
                        si = st.session_state['accounts'][nome].setdefault('saldos_iniciais', {}).setdefault(p, {'Capital': 0.0, 'Custeio': 0.0})
                        k = f"{nome}_{p}"
                        cols = st.columns([2, 1, 1, 1])
                        cols[0].write(f"📂 {p}")
                        
                        # ALTERAÇÃO AQUI: Nomes explícitos para evitar erro de tradução
                        n_cap = cols[1].number_input("Saldo Inicial Capital", value=si['Capital'], key=f"sic_{k}")
                        n_cus = cols[2].number_input("Saldo Inicial Custeio", value=si['Custeio'], key=f"sis_{k}")
                        
                        if cols[3].button("Salvar", key=f"bts_{k}"):
                            si['Capital'] = n_cap
                            si['Custeio'] = n_cus
                            save_account_to_firebase(st.session_state['db_conn'], nome, st.session_state['accounts'][nome])
                            st.rerun()

            if st.session_state['accounts'][nome]['programas']:
                anos = sorted(st.session_state.get('available_years', [datetime.now().year]))
                for aba_ano, ano in zip(st.tabs([str(a) for a in anos]), anos):
                    with aba_ano:
                        render_year_view(nome, ano, st.session_state['accounts'][nome]['programas'])
            else:
                st.warning("Cadastre programas acima.")

if __name__ == "__main__":
    main()