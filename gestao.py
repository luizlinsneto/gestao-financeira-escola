import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os
import base64
import io
import textwrap

# --- TENTATIVA DE IMPORTAR REPORTLAB ---
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão Financeira Escolar", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .stNumberInput input { text-align: right; }
    .big-font { font-size: 18px !important; font-weight: bold; }
    div[data-testid="stMetricValue"] { font-size: 24px; }
    .download-box {
        padding: 10px;
        background-color: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-radius: 5px;
        margin-bottom: 5px;
        font-size: 14px;
        text-align: center;
    }
    .row-header { font-weight: bold; border-bottom: 2px solid #ddd; padding: 5px; }
    .warning-box {
        padding: 10px;
        background-color: #fef2f2;
        border: 1px solid #fecaca;
        border-radius: 5px;
        color: #991b1b;
        margin-top: 10px;
    }
    .info-box {
        padding: 10px;
        background-color: #e0f2f1;
        border: 1px solid #b2dfdb;
        border-radius: 5px;
        color: #004d40;
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONEXÃO COM FIREBASE ---
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        cred = None
        if os.path.exists("firebase_key.json"):
            try:
                cred = credentials.Certificate("firebase_key.json")
            except Exception as e:
                st.error(f"Erro no arquivo json local: {e}")
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

# --- FUNÇÕES DE SESSÃO ---
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
            st.session_state['empenhos_global'] = load_empenhos_from_firebase(db)
        else:
            st.session_state['empenhos_global'] = []

    if 'global_programs' not in st.session_state:
        if db:
            st.session_state['global_programs'] = load_global_programs_from_firebase(db)
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

# --- FUNÇÕES CRUD ---
def load_accounts_from_firebase(db):
    if db is None: return {}
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
    if db is None: return []
    try:
        doc = db.collection('pdde_dados_gerais').document('empenhos').get()
        if doc.exists:
            return doc.to_dict().get('lista', [])
        return []
    except Exception as e:
        return []

def load_global_programs_from_firebase(db):
    if db is None: return []
    try:
        doc = db.collection('pdde_dados_gerais').document('programas_globais').get()
        if doc.exists:
            return doc.to_dict().get('lista', [])
        return []
    except Exception as e:
        return []

# --- FUNÇÕES ARQUIVOS (AGORA COM 3 ARQUIVOS) ---
def save_files_to_firebase(db, empenho_id, file_emp, file_nf, file_comprovante):
    if db is None: return False
    try:
        doc_ref = db.collection('pdde_arquivos').document(empenho_id)
        update_data = {}
        
        # Processa Arquivo do Empenho
        if file_emp:
            if file_emp.size > 2 * 1024 * 1024:
                st.warning(f"Arquivo do Empenho muito grande ({file_emp.name}). Limite 2MB.")
            else:
                file_bytes = file_emp.read()
                b64_string = base64.b64encode(file_bytes).decode('utf-8')
                update_data['emp_name'] = file_emp.name
                update_data['emp_data'] = b64_string

        # Processa Nota Fiscal
        if file_nf:
            if file_nf.size > 2 * 1024 * 1024:
                st.warning(f"Nota Fiscal muito grande ({file_nf.name}). Limite 2MB.")
            else:
                file_bytes = file_nf.read()
                b64_string = base64.b64encode(file_bytes).decode('utf-8')
                update_data['nf_name'] = file_nf.name
                update_data['nf_data'] = b64_string
        
        # Processa Comprovante
        if file_comprovante:
            if file_comprovante.size > 2 * 1024 * 1024:
                st.warning(f"Comprovante muito grande ({file_comprovante.name}). Limite 2MB.")
            else:
                file_bytes = file_comprovante.read()
                b64_string = base64.b64encode(file_bytes).decode('utf-8')
                update_data['comp_name'] = file_comprovante.name
                update_data['comp_data'] = b64_string

        if update_data:
            doc_ref.set(update_data, merge=True)
            return True
        return True 
    except Exception as e:
        st.error(f"Erro ao salvar arquivos: {e}")
        return False

def get_files_from_firebase(db, empenho_id):
    if db is None: return {}
    try:
        doc = db.collection('pdde_arquivos').document(empenho_id).get()
        if doc.exists:
            return doc.to_dict()
        return {}
    except:
        return {}

def delete_file_from_firebase(db, empenho_id):
    if db is None: return
    try:
        db.collection('pdde_arquivos').document(empenho_id).delete()
    except:
        pass

# --- FUNÇÕES SALVAMENTO ---
def save_account_to_firebase(db, account_name, account_data):
    if db is None: return
    try:
        db.collection('pdde_contas').document(account_name).set(account_data)
    except Exception as e:
        st.error(f"Erro ao salvar conta: {e}")

def delete_account_from_firebase(db, account_name):
    if db is None: return
    try:
        db.collection('pdde_contas').document(account_name).delete()
    except Exception as e:
        st.error(f"Erro ao excluir conta: {e}")

def rename_account_in_firebase(db, old_name, new_name):
    if db is None: return False
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
    if db is None: return
    try:
        db.collection('pdde_dados_gerais').document('empenhos').set({'lista': lista_empenhos})
    except Exception as e:
        st.error(f"Erro ao salvar empenhos: {e}")

def save_global_programs_to_firebase(db, lista_programas):
    if db is None: return
    try:
        db.collection('pdde_dados_gerais').document('programas_globais').set({'lista': lista_programas})
    except Exception as e:
        st.error(f"Erro ao salvar programas globais: {e}")

# --- AUXILIARES (GLOBAIS) ---
def format_currency(value):
    if value is None: value = 0.0
    s = "{:,.2f}".format(value)
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"

def apply_currency_format(df, cols):
    for col in cols:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    return df

def safe_date(date_str):
    if not date_str: return None
    try: return datetime.strptime(date_str, "%Y-%m-%d").date()
    except: return None

# --- GERADOR DE PDF ---
def create_empenho_pdf(data_dict):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    c.setTitle(f"Empenho_{data_dict.get('numero_empenho')}")
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, height - 2 * cm, "RELATÓRIO DE EMPENHO / ORDEM DE PAGAMENTO")
    c.line(2 * cm, height - 2.2 * cm, width - 2 * cm, height - 2.2 * cm)
    
    y = height - 3.5 * cm
    left_margin = 2 * cm
    
    def draw_pair(label, value, x_offset, y_pos):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x_offset, y_pos, f"{label}:")
        c.setFont("Helvetica", 10)
        c.drawString(x_offset + 3.5 * cm, y_pos, str(value) if value else "-")

    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.darkblue)
    c.drawString(left_margin, y, "1. DADOS DO EMPENHO")
    c.setFillColor(colors.black)
    y -= 0.8 * cm
    
    d_emp = datetime.strptime(data_dict.get('data_empenho'), "%Y-%m-%d").strftime("%d/%m/%Y") if data_dict.get('data_empenho') else "-"
    draw_pair("Programa", data_dict.get('programa'), left_margin, y)
    y -= 0.6 * cm
    draw_pair("Nº Empenho", data_dict.get('numero_empenho'), left_margin, y)
    y -= 0.6 * cm
    draw_pair("Data Empenho", d_emp, left_margin, y)
    y -= 0.6 * cm
    val_fmt = format_currency(float(data_dict.get('valor', 0)))
    draw_pair("Valor Total", val_fmt, left_margin, y)
    
    y -= 1.5 * cm
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.darkblue)
    c.drawString(left_margin, y, "2. DADOS DE PAGAMENTO E EXECUÇÃO")
    c.setFillColor(colors.black)
    y -= 0.8 * cm
    
    d_ob = datetime.strptime(data_dict.get('data_ob'), "%Y-%m-%d").strftime("%d/%m/%Y") if data_dict.get('data_ob') else "-"
    d_nf = datetime.strptime(data_dict.get('data_nota_fiscal'), "%Y-%m-%d").strftime("%d/%m/%Y") if data_dict.get('data_nota_fiscal') else "-"
    
    draw_pair("Nº Ordem Banc.", data_dict.get('ordem_bancaria'), left_margin, y)
    draw_pair("Data OB", d_ob, left_margin + 9 * cm, y)
    y -= 0.6 * cm
    draw_pair("Status Atual", data_dict.get('status'), left_margin, y)
    draw_pair("Data Nota Fiscal", d_nf, left_margin + 9 * cm, y)
    
    y -= 1.5 * cm
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.darkblue)
    c.drawString(left_margin, y, "3. DETALHAMENTO / ITENS")
    c.setFillColor(colors.black)
    y -= 0.8 * cm
    
    c.setFont("Helvetica", 10)
    text = c.beginText(left_margin, y)
    text.setFont("Helvetica", 10)
    
    itens_desc = data_dict.get('itens', 'Sem descrição.')
    obs_desc = data_dict.get('observacao', '')
    
    lines = textwrap.wrap(itens_desc, width=85)
    for line in lines:
        text.textLine(line)
    c.drawText(text)
    
    y -= (len(lines) * 0.5 * cm) + 1.0 * cm
    
    if obs_desc:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left_margin, y, "Observações:")
        y -= 0.5 * cm
        c.setFont("Helvetica", 10)
        c.drawString(left_margin, y, obs_desc)
        y -= 2 * cm
    else:
        y -= 1.5 * cm

    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width / 2, y - 0.5 * cm, "Luiz de Albuquerque Lins Neto")
    c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2, y - 1.0 * cm, "Assistente de Gestão")
    
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(left_margin, 2 * cm, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} - Sistema de Gestão de Empenhos")
    
    c.save()
    buffer.seek(0)
    return buffer

def get_saldo_anterior(account_name, programa, tipo_recurso, mes_alvo, ano_alvo):
    conta_data = st.session_state['accounts'][account_name]
    movs = conta_data.get('movimentacoes', []) 
    saldo = 0.0
    
    saldos_anuais = conta_data.get('saldos_anuais', {})
    str_ano = str(ano_alvo)
    
    dados_ano_atual = saldos_anuais.get(str_ano, {})
    dados_prog_ano = dados_ano_atual.get(programa, {})
    
    val_cap = dados_prog_ano.get('Capital', 0.0)
    val_cust = dados_prog_ano.get('Custeio', 0.0)
    
    if tipo_recurso == 'Capital':
        saldo += val_cap
    elif tipo_recurso == 'Custeio':
        saldo += val_cust
    elif tipo_recurso == 'Total':
        saldo += (val_cap + val_cust)

    for mov in movs:
        try:
            mov_ano = int(mov.get('ano', datetime.now().year))
        except:
            mov_ano = datetime.now().year
            
        mov_mes = mov['mes_num']
        
        eh_ano_correto = (mov_ano == int(ano_alvo))
        eh_mes_anterior = (mov_mes < int(mes_alvo))
        
        if mov['programa'] == programa and eh_ano_correto and eh_mes_anterior:
            if tipo_recurso == 'Capital':
                saldo += (mov['credito_capital'] + mov['rendimento_capital'] - mov['debito_capital'])
            elif tipo_recurso == 'Custeio':
                saldo += (mov['credito_custeio'] + mov['rendimento_custeio'] - mov['debito_custeio'])
            elif tipo_recurso == 'Total':
                saldo += (mov['total_credito'] + mov['total_rendimento'] - mov['total_debito'])
    return saldo

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
        fator_cap = base_prog['Capital'] / total_saldo_conta if total_saldo_conta > 0 else 0
        fator_cus = base_prog['Custeio'] / total_saldo_conta if total_saldo_conta > 0 else 0
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

def sidebar_config():
    if st.session_state['db_conn'] is None:
        st.sidebar.error("⚠️ Sem conexão com Banco de Dados")
    
    if st.sidebar.button("🔄 Recarregar Dados", help="Use se notar dados desatualizados"):
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
            conta_selecionada = st.sidebar.selectbox("📂 Selecione a Conta", options=contas_existentes, key="sidebar_conta_select")
            dados_conta_atual = st.session_state['accounts'].get(conta_selecionada, {})
            progs_conta = dados_conta_atual.get('programas', [])
            if progs_conta:
                st.sidebar.markdown("**📌 Programas Vinculados:**")
                texto_progs = "\n".join([f"• {p}" for p in progs_conta])
                st.sidebar.text(texto_progs.replace("• ", "")) 
            else:
                st.sidebar.caption("Nenhum programa vinculado.")
            st.sidebar.divider()

        with st.sidebar.expander("⚙️ Gerenciar Contas"):
            tab_criar, tab_renomear, tab_del = st.tabs(["Criar", "Renomear", "Excluir"])
            with tab_criar:
                nova_conta = st.text_input("Nome da Nova Conta", placeholder="Ex: 27.922-6")
                if st.button("Adicionar Conta"):
                    if nova_conta and nova_conta not in st.session_state['accounts']:
                        nova_estrutura = {
                            'programas': [], 
                            'movimentacoes': [], 
                            'saldos_iniciais': {}, 
                            'saldos_anuais': {} 
                        }
                        st.session_state['accounts'][nova_conta] = nova_estrutura
                        save_account_to_firebase(st.session_state['db_conn'], nova_conta, nova_estrutura)
                        st.success(f"Conta {nova_conta} criada!")
                        st.rerun()
                    elif nova_conta in st.session_state['accounts']:
                        st.warning("Conta já existe.")
            with tab_renomear:
                if contas_existentes:
                    conta_alvo = st.selectbox("Conta Atual:", contas_existentes, key="sel_ren_acc")
                    novo_nome_conta = st.text_input("Novo Nome:", key="ipt_ren_acc")
                    if st.button("✏️ Renomear", type="primary"):
                        if novo_nome_conta and novo_nome_conta not in contas_existentes:
                            success = rename_account_in_firebase(st.session_state['db_conn'], conta_alvo, novo_nome_conta)
                            if success:
                                if conta_alvo in st.session_state['accounts']:
                                    dados = st.session_state['accounts'].pop(conta_alvo)
                                    st.session_state['accounts'][novo_nome_conta] = dados
                                    st.success(f"Renomeado para {novo_nome_conta}!")
                                    st.rerun()
                        elif novo_nome_conta in contas_existentes:
                            st.warning("Nome já existe!")
                else:
                    st.info("Sem contas.")
            with tab_del:
                if contas_existentes:
                    conta_del = st.selectbox("Apagar Conta:", contas_existentes, key="sel_del_acc")
                    if st.button(f"🗑️ Excluir {conta_del}", type="primary"):
                        if conta_del in st.session_state['accounts']:
                            del st.session_state['accounts'][conta_del]
                            delete_account_from_firebase(st.session_state['db_conn'], conta_del)
                            st.success(f"Conta {conta_del} excluída!")
                            st.rerun()
                else:
                    st.info("Nenhuma conta para excluir.")

    with st.sidebar.expander("📅 Gerenciar Exercícios (Anos)"):
        novo_ano = st.number_input("Adicionar Ano", min_value=2000, max_value=2050, value=datetime.now().year + 1, step=1)
        if st.button("Criar Novo Exercício"):
            if novo_ano not in st.session_state['available_years']:
                st.session_state['available_years'].append(novo_ano)
                st.session_state['available_years'].sort()
                st.success(f"Exercício de {novo_ano} adicionado!")
                st.rerun()
            else:
                st.warning("Este ano já existe.")
    return modulo_selecionado, conta_selecionada

def render_financeiro_view(conta_atual, ano_atual, programas):
    tab_lanc, tab_rel, tab_resumo = st.tabs(["📝 Lançamentos", "📑 Extrato Mensal", "📊 Resumo Geral"])

    with tab_lanc:
        col_mes, col_rend = st.columns([1, 2])
        meses = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 
                 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
        with col_mes:
            mes_selecionado = st.selectbox("Mês", options=list(meses.keys()), format_func=lambda x: meses[x], key=f"sel_mes_{conta_atual}_{ano_atual}")
        
        movs = st.session_state['accounts'][conta_atual].get('movimentacoes', [])
        registros_existentes = [m for m in movs if m['mes_num'] == mes_selecionado and m.get('ano', datetime.now().year) == ano_atual]
        val_rendimento_inicial = sum([m['total_rendimento'] for m in registros_existentes]) if registros_existentes else 0.0
        if registros_existentes: st.info(f"✏️ Editando dados de {meses[mes_selecionado]}.")

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
            prog_data = next((m for m in registros_existentes if m['programa'] == prog), None)
            v_cc = float(prog_data['credito_capital']) if prog_data else 0.0
            v_crc = float(prog_data['credito_custeio']) if prog_data else 0.0
            v_dc = float(prog_data['debito_capital']) if prog_data else 0.0
            v_dec = float(prog_data['debito_custeio']) if prog_data else 0.0

            saldo_disp_cap = get_saldo_anterior(conta_atual, prog, 'Capital', mes_selecionado, ano_atual)
            saldo_disp_cust = get_saldo_anterior(conta_atual, prog, 'Custeio', mes_selecionado, ano_atual)

            with st.expander(f"Movimento: {prog}", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                st.markdown(f"**Saldo Ant. ({ano_atual}):** Cap: {format_currency(saldo_disp_cap)} | Cust: {format_currency(saldo_disp_cust)}")
                k_suf = f"{conta_atual}_{prog}_{ano_atual}_{mes_selecionado}"
                cred_cap = c1.number_input(f"Créd. Capital", min_value=0.0, value=v_cc, key=f"cc_{k_suf}")
                cred_cus = c2.number_input(f"Créd. Custeio", min_value=0.0, value=v_crc, key=f"crc_{k_suf}")
                deb_cap = c3.number_input(f"Déb. Capital", min_value=0.0, value=v_dc, key=f"dc_{k_suf}")
                deb_cus = c4.number_input(f"Déb. Custeio", min_value=0.0, value=v_dec, key=f"dec_{k_suf}")
                
                saldo_proj_cap = saldo_disp_cap + cred_cap - deb_cap
                saldo_proj_cust = saldo_disp_cust + cred_cus - deb_cus
                if saldo_proj_cap < 0:
                    st.error(f"⚠️ Atenção: Saldo de Capital ficará negativo ({format_currency(saldo_proj_cap)})!")
                    has_error = True
                if saldo_proj_cust < 0:
                    st.error(f"⚠️ Atenção: Saldo de Custeio ficará negativo ({format_currency(saldo_proj_cust)})!")
                    has_error = True
                dados_entrada[prog] = {'cred_cap': cred_cap, 'cred_cus': cred_cus, 'deb_cap': deb_cap, 'deb_cus': deb_cus}

        if st.button(f"💾 Salvar Lançamento {meses[mes_selecionado]}/{ano_atual}", type="primary", key=f"btn_save_{conta_atual}_{ano_atual}_{mes_selecionado}"):
            if has_error: st.error("❌ Não é possível salvar pois há saldos negativos. Verifique os valores.")
            else:
                novos = calcular_rateio_rendimento(conta_atual, mes_selecionado, ano_atual, rendimento_total, dados_entrada)
                lista_atual = st.session_state['accounts'][conta_atual].get('movimentacoes', [])
                lista_limpa = [m for m in lista_atual if not (m['mes_num'] == mes_selecionado and m.get('ano', datetime.now().year) == ano_atual)]
                lista_limpa.extend(novos)
                st.session_state['accounts'][conta_atual]['movimentacoes'] = lista_limpa
                save_account_to_firebase(st.session_state['db_conn'], conta_atual, st.session_state['accounts'][conta_atual])
                st.success("Dados salvos com sucesso!")
                st.rerun()

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
                    "Créd. Cap.": m['credito_capital'], "Créd. Cust.": m['credito_custeio'], "Créd. Total": m['total_credito'],
                    "Rend. Cap.": m['rendimento_capital'], "Rend. Cust.": m['rendimento_custeio'], "Rend. Total": m['total_rendimento'],
                    "Déb. Cap.": m['debito_capital'], "Déb. Cust.": m['debito_custeio'], "Déb. Total": m['total_debito'],
                    "S. Custeio": saldo_acumulado_cus, "S. Capital": saldo_acumulado_cap, "S. Total": saldo_total
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
                df_final = pd.concat([df_final, df_prog, linha_total], ignore_index=True)

        if not df_final.empty:
            def highlight_total(row):
                return ['background-color: #ffd700; color: black; font-weight: bold'] * len(row) if row['Programa'] == 'TOTAL' else [''] * len(row)
            
            cols_to_format = [
                "Créd. Cap.", "Créd. Cust.", "Créd. Total",
                "Rend. Cap.", "Rend. Cust.", "Rend. Total",
                "Déb. Cap.", "Déb. Cust.", "Déb. Total",
                "S. Custeio", "S. Capital", "S. Total"
            ]
            df_display = apply_currency_format(df_final.copy(), cols_to_format)
            st.dataframe(df_display.style.apply(highlight_total, axis=1), use_container_width=True, height=500)
        else: st.info(f"Nenhuma movimentação em {ano_atual}.")
    
    with tab_resumo:
        st.markdown("### 📊 Resumo Geral e Demonstrativo da Conta")
        st.divider()
        st.markdown("#### 📑 Simulação do Demonstrativo (Bloco 2)")
        prog_demo = st.selectbox("Selecione o Programa para Detalhar:", options=programas, key=f"sel_demo_{conta_atual}_{ano_atual}")
        
        if prog_demo:
            s_reprog_cap = get_saldo_anterior(conta_atual, prog_demo, 'Capital', 1, ano_atual)
            s_reprog_cust = get_saldo_anterior(conta_atual, prog_demo, 'Custeio', 1, ano_atual)
            
            st.markdown(f"""
            <div class="info-box">
                Mostrando dados para: <b>{prog_demo}</b><br>
                Saldo Reprogramado Encontrado: <b>{format_currency(s_reprog_cap + s_reprog_cust)}</b>
                (Capital: {format_currency(s_reprog_cap)} | Custeio: {format_currency(s_reprog_cust)})
            </div>
            """, unsafe_allow_html=True)
            
            rec_prop_cust = 0.0
            rec_prop_cap = 0.0
            devol_cust = 0.0
            devol_cap = 0.0

            movs = st.session_state['accounts'][conta_atual].get('movimentacoes', [])
            movs_demo = [m for m in movs if m['programa'] == prog_demo and m.get('ano') == ano_atual]
            
            cred_cust = sum(m['credito_custeio'] for m in movs_demo)
            cred_cap = sum(m['credito_capital'] for m in movs_demo)
            rend_cust = sum(m['rendimento_custeio'] for m in movs_demo)
            rend_cap = sum(m['rendimento_capital'] for m in movs_demo)
            desp_cust = sum(m['debito_custeio'] for m in movs_demo)
            desp_cap = sum(m['debito_capital'] for m in movs_demo)

            total_rec_cust = s_reprog_cust + cred_cust + rec_prop_cust + rend_cust - devol_cust
            total_rec_cap = s_reprog_cap + cred_cap + rec_prop_cap + rend_cap - devol_cap
            saldo_final_cust = total_rec_cust - desp_cust
            saldo_final_cap = total_rec_cap - desp_cap
            
            if saldo_final_cust < 0 or saldo_final_cap < 0:
                st.markdown(f"""
                <div class="warning-box">
                    ⚠️ <b>Atenção: Entradas menores que Saídas!</b><br>
                    Verifique se o <b>Saldo Anterior</b> foi configurado corretamente em 'Gerenciar Programas'.<br>
                    Receita Total Custeio: {format_currency(total_rec_cust)} | Despesa: {format_currency(desp_cust)}
                </div>
                """, unsafe_allow_html=True)

            df_demo = pd.DataFrame([
                {"Descrição": "08 - Saldo Reprogramado", "Custeio": s_reprog_cust, "Capital": s_reprog_cap},
                {"Descrição": "09 - Valor Creditado", "Custeio": cred_cust, "Capital": cred_cap},
                {"Descrição": "10 - Recursos Próprios", "Custeio": rec_prop_cust, "Capital": rec_prop_cap},
                {"Descrição": "11 - Rendimento de Aplicação", "Custeio": rend_cust, "Capital": rend_cap},
                {"Descrição": "12 - Devolução de Recursos (-)", "Custeio": devol_cust, "Capital": devol_cap},
                {"Descrição": "13 - VALOR TOTAL RECEITA", "Custeio": total_rec_cust, "Capital": total_rec_cap},
                {"Descrição": "14 - Despesas Realizadas", "Custeio": desp_cust, "Capital": desp_cap},
                {"Descrição": "15 - Saldo a Reprogramar", "Custeio": saldo_final_cust, "Capital": saldo_final_cap},
            ])
            df_demo["Total"] = df_demo["Custeio"] + df_demo["Capital"]
            
            def highlight_demo_rows(row):
                if "13 - VALOR" in row['Descrição'] or "15 - Saldo" in row['Descrição']:
                    return ['background-color: #e0f2f1; color: black; font-weight: bold'] * len(row)
                return [''] * len(row)
            
            df_demo_display = apply_currency_format(df_demo.copy(), ["Custeio", "Capital", "Total"])
            st.dataframe(df_demo_display.style.apply(highlight_demo_rows, axis=1), use_container_width=True, height=350)
        
        with st.expander("Ver Resumo Geral de Todos os Programas"):
            dados_resumo = []
            conta_dados = st.session_state['accounts'][conta_atual]
            if 'extra_fields' not in conta_dados: conta_dados['extra_fields'] = {}

            for prog in programas:
                saldo_anterior = get_saldo_anterior(conta_atual, prog, 'Total', 1, ano_atual)
                movs_ano = [m for m in movs if m['programa'] == prog and m.get('ano') == ano_atual]
                
                credito_ano = sum(m['total_credito'] for m in movs_ano)
                rendimento_ano = sum(m['total_rendimento'] for m in movs_ano)
                debito_ano = sum(m['total_debito'] for m in movs_ano)
                
                chave_extras = f"{prog}_{ano_atual}"
                extras_p = conta_dados['extra_fields'].get(chave_extras, {})
                
                ajuste_entradas = extras_p.get('rec_prop_cust', 0) + extras_p.get('rec_prop_cap', 0)
                ajuste_saidas = extras_p.get('devol_cust', 0) + extras_p.get('devol_cap', 0)
                
                saldo_final = saldo_anterior + credito_ano + rendimento_ano + ajuste_entradas - debito_ano - ajuste_saidas
                
                dados_resumo.append({
                    "Programas": prog, 
                    f"Saldo Inicial {ano_atual}": saldo_anterior, 
                    f"Crédito {ano_atual}": credito_ano + ajuste_entradas, 
                    f"Rendimentos {ano_atual}": rendimento_ano, 
                    f"Débitos {ano_atual}": debito_ano + ajuste_saidas,
                    f"Saldo 31.12.{ano_atual}": saldo_final
                })
                
            if dados_resumo:
                df_resumo = pd.DataFrame(dados_resumo)
                cols_num = [c for c in df_resumo.columns if c != "Programas"]
                linha_total = {"Programas": "TOTAL GERAL"}
                for c in cols_num: linha_total[c] = df_resumo[c].sum()
                
                df_resumo = pd.concat([df_resumo, pd.DataFrame([linha_total])], ignore_index=True)
                def highlight_total_resumo(row):
                    return ['background-color: #ffd700; color: black; font-weight: bold'] * len(row) if row['Programas'] == 'TOTAL GERAL' else [''] * len(row)
                
                df_resumo_display = apply_currency_format(df_resumo.copy(), cols_num)
                st.dataframe(df_resumo_display.style.apply(highlight_total_resumo, axis=1), use_container_width=True)

def render_resumo_consolidado_view():
    st.subheader("📈 Resumo Geral Consolidado (Todas as Contas)")
    anos_disp = sorted(st.session_state.get('available_years', [datetime.now().year]))
    str_anos = [str(a) for a in anos_disp]
    ano_selecionado = st.selectbox("Selecione o Ano:", str_anos, index=len(str_anos)-1, key="sel_ano_consol")
    ano_int = int(ano_selecionado)
    
    total_recebido = 0.0
    total_gasto = 0.0
    total_saldo_atual = 0.0
    lista_detalhada = []
    
    for nome_conta, dados_conta in st.session_state['accounts'].items():
        movs = dados_conta.get('movimentacoes', [])
        progs = dados_conta.get('programas', [])
        movs_ano = [m for m in movs if m.get('ano') == ano_int]
        
        if 'extra_fields' not in dados_conta: dados_conta['extra_fields'] = {}

        saldo_inicial_conta = 0.0
        creditos_conta = sum(m['total_credito'] for m in movs_ano)
        rendimentos_conta = sum(m['total_rendimento'] for m in movs_ano)
        debitos_conta = sum(m['total_debito'] for m in movs_ano)
        
        ajuste_entradas_conta = 0.0
        ajuste_saidas_conta = 0.0

        for p in progs:
            saldo_inicial_conta += get_saldo_anterior(nome_conta, p, 'Total', 1, ano_int)
            chave_extras = f"{p}_{ano_int}"
            extras_p = dados_conta['extra_fields'].get(chave_extras, {})
            ajuste_entradas_conta += (extras_p.get('rec_prop_cust', 0) + extras_p.get('rec_prop_cap', 0))
            ajuste_saidas_conta += (extras_p.get('devol_cust', 0) + extras_p.get('devol_cap', 0))
        
        receita_total_conta = saldo_inicial_conta + creditos_conta + rendimentos_conta + ajuste_entradas_conta
        saldo_final_conta = receita_total_conta - debitos_conta - ajuste_saidas_conta
        
        total_recebido += (saldo_inicial_conta + creditos_conta + rendimentos_conta + ajuste_entradas_conta)
        total_gasto += (debitos_conta + ajuste_saidas_conta)
        total_saldo_atual += saldo_final_conta
        
        lista_detalhada.append({
            "Conta": nome_conta,
            "Saldo Anterior": saldo_inicial_conta,
            "Créditos (+RP)": creditos_conta + ajuste_entradas_conta,
            "Rendimentos": rendimentos_conta,
            "Débitos (+Dev)": debitos_conta + ajuste_saidas_conta,
            "Saldo Final": saldo_final_conta
        })
        
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Receita (Disp.)", format_currency(total_recebido), delta_color="normal")
    col2.metric("Total Saídas (Débitos)", format_currency(total_gasto), delta_color="inverse")
    col3.metric("Saldo Geral Acumulado", format_currency(total_saldo_atual))
    st.divider()
    
    st.markdown(f"#### Detalhamento por Conta - {ano_int}")
    if lista_detalhada:
        df_resumo = pd.DataFrame(lista_detalhada)
        linha_total = {
            "Conta": "TOTAL GERAL",
            "Saldo Anterior": df_resumo["Saldo Anterior"].sum(),
            "Créditos (+RP)": df_resumo["Créditos (+RP)"].sum(),
            "Rendimentos": df_resumo["Rendimentos"].sum(),
            "Débitos (+Dev)": df_resumo["Débitos (+Dev)"].sum(),
            "Saldo Final": df_resumo["Saldo Final"].sum()
        }
        df_resumo = pd.concat([df_resumo, pd.DataFrame([linha_total])], ignore_index=True)
        def highlight_total(row):
            return ['background-color: #ffd700; color: black; font-weight: bold'] * len(row) if row['Conta'] == 'TOTAL GERAL' else [''] * len(row)
        
        cols_to_fmt = ["Saldo Anterior", "Créditos (+RP)", "Rendimentos", "Débitos (+Dev)", "Saldo Final"]
        df_resumo_display = apply_currency_format(df_resumo.copy(), cols_to_fmt)

        st.dataframe(
            df_resumo_display.style.apply(highlight_total, axis=1),
            use_container_width=True,
            height=400
        )
    else: st.info("Nenhuma conta encontrada.")

def render_empenhos_global_view():
    st.subheader("📜 Controle de Empenhos e Ordens de Pagamento")
    
    if not HAS_REPORTLAB:
        st.warning("⚠️ Biblioteca 'reportlab' não encontrada. A geração de PDF estará desabilitada.")

    with st.expander("⚙️ Cadastrar/Gerenciar Programas"):
        c_p1, c_p2 = st.columns([3, 1])
        novo_prog_global = c_p1.text_input("Novo Programa", key="new_prog_global")
        if c_p2.button("Cadastrar", key="btn_add_prog_global"):
            if novo_prog_global and novo_prog_global not in st.session_state['global_programs']:
                st.session_state['global_programs'].append(novo_prog_global)
                save_global_programs_to_firebase(st.session_state['db_conn'], st.session_state['global_programs'])
                st.success("Programa cadastrado!")
                st.rerun()
            elif novo_prog_global:
                st.warning("Programa já existe.")
        
        if st.session_state['global_programs']:
            st.write("Programas cadastrados: " + ", ".join(st.session_state['global_programs']))
        else:
            st.info("Nenhum programa cadastrado para empenhos.")

    if 'empenho_mode' not in st.session_state:
        st.session_state['empenho_mode'] = 'list'
    
    if 'empenho_em_edicao' not in st.session_state:
        st.session_state['empenho_em_edicao'] = None

    if st.session_state['empenho_mode'] == 'list':
        col_new, _ = st.columns([1, 4])
        if col_new.button("➕ Novo Empenho", type="primary"):
            st.session_state['empenho_em_edicao'] = None
            st.session_state['empenho_mode'] = 'form'
            st.rerun()

        st.divider()
        anos_disp = sorted(st.session_state.get('available_years', [datetime.now().year]))
        str_anos = [str(a) for a in anos_disp]
        ano_filtro = st.radio("Filtrar por Ano:", str_anos, horizontal=True, index=len(str_anos)-1)
        
        lista_programas = st.session_state['global_programs']
        if not lista_programas: lista_programas = ["Sem cadastro"]
        filtro_prog_emp = st.selectbox("Filtrar por Programa", ["Todos"] + lista_programas, key="filt_gemp")

        todos_empenhos = st.session_state['empenhos_global']
        empenhos_ano = []
        for emp in todos_empenhos:
            try:
                dt = datetime.strptime(emp.get('data_empenho', ''), "%Y-%m-%d")
                if str(dt.year) == ano_filtro:
                    empenhos_ano.append(emp)
            except: pass
        empenhos_ano.sort(key=lambda x: x.get('data_empenho', ''), reverse=True)

        lista_final = empenhos_ano
        if filtro_prog_emp != "Todos":
            lista_final = [e for e in empenhos_ano if e['programa'] == filtro_prog_emp]

        st.markdown(f"**Registros Encontrados: {len(lista_final)}**")

        if lista_final:
            c1, c2, c3, c4, c5, c6, c7 = st.columns([1.2, 2, 1, 1.2, 1.2, 0.8, 0.8])
            c1.markdown("<div class='row-header'>Data</div>", unsafe_allow_html=True)
            c2.markdown("<div class='row-header'>Programa</div>", unsafe_allow_html=True)
            c3.markdown("<div class='row-header'>Nº Emp.</div>", unsafe_allow_html=True)
            c4.markdown("<div class='row-header'>Valor</div>", unsafe_allow_html=True)
            c5.markdown("<div class='row-header'>Status</div>", unsafe_allow_html=True)
            c6.markdown("<div class='row-header'>PDF</div>", unsafe_allow_html=True)
            c7.markdown("<div class='row-header'>Ação</div>", unsafe_allow_html=True)

            for item in lista_final:
                with st.container():
                    col1, col2, col3, col4, col5, col6, col7 = st.columns([1.2, 2, 1, 1.2, 1.2, 0.8, 0.8])
                    try: d_show = datetime.strptime(item.get('data_empenho', ''), "%Y-%m-%d").strftime("%d/%m/%Y")
                    except: d_show = "-"
                    val_show = format_currency(float(item.get('valor', 0)))
                    
                    col1.text(d_show)
                    col2.text(item.get('programa', '-'))
                    col3.text(item.get('numero_empenho', '-'))
                    col4.text(val_show)
                    col5.text(item.get('status', '-'))
                    
                    if HAS_REPORTLAB:
                        pdf_data = create_empenho_pdf(item)
                        col6.download_button("📄", data=pdf_data, file_name=f"empenho_{item.get('numero_empenho')}.pdf", mime='application/pdf', key=f"btn_pdf_{item['id']}")
                    else:
                        col6.text("-")

                    if col7.button("✏️", key=f"btn_edit_{item['id']}"):
                        st.session_state['empenho_em_edicao'] = item
                        st.session_state['empenho_mode'] = 'form'
                        st.rerun()
                    st.markdown("<div style='border-bottom: 1px solid #eee; margin-bottom: 5px;'></div>", unsafe_allow_html=True)
            
            total_val = sum([float(i.get('valor', 0)) for i in lista_final])
            st.metric("Total (Filtro)", format_currency(total_val))
        else:
            st.info("Nenhum registro encontrado com os filtros atuais.")

    elif st.session_state['empenho_mode'] == 'form':
        if st.button("⬅️ Voltar para a Lista", key="btn_back_top"):
            st.session_state['empenho_mode'] = 'list'
            st.rerun()
        st.divider()

        dados_edicao = st.session_state['empenho_em_edicao']
        is_edit_mode = dados_edicao is not None
        
        val_prog = dados_edicao.get('programa') if is_edit_mode else None
        val_num = dados_edicao.get('numero_empenho', "") if is_edit_mode else ""
        val_data = safe_date(dados_edicao.get('data_empenho')) if is_edit_mode else None
        val_ob = dados_edicao.get('ordem_bancaria', "") if is_edit_mode else ""
        val_data_ob = safe_date(dados_edicao.get('data_ob')) if is_edit_mode else None
        val_valor = float(dados_edicao.get('valor', 0.0)) if is_edit_mode else 0.0
        val_data_nf = safe_date(dados_edicao.get('data_nota_fiscal', dados_edicao.get('data_utilizacao', ''))) if is_edit_mode else None
        val_status = dados_edicao.get('status', "PENDENTE") if is_edit_mode else "PENDENTE"
        val_obs = dados_edicao.get('observacao', "") if is_edit_mode else ""
        val_itens = dados_edicao.get('itens', "") if is_edit_mode else ""
        
        current_files = {}
        if is_edit_mode:
            with st.spinner("Carregando anexos..."):
                current_files = get_files_from_firebase(st.session_state['db_conn'], dados_edicao.get('id'))

        lista_programas = st.session_state['global_programs']
        if not lista_programas: lista_programas = ["Sem cadastro"]
        
        try:
            prog_index = lista_programas.index(val_prog) if (is_edit_mode and val_prog in lista_programas) else 0
        except ValueError:
            prog_index = 0

        titulo = "✏️ Editando Empenho" if is_edit_mode else "➕ Novo Empenho"
        st.markdown(f"### {titulo}")
        
        if is_edit_mode and HAS_REPORTLAB:
            pdf_data = create_empenho_pdf(dados_edicao)
            st.download_button("📄 Gerar Relatório em PDF", data=pdf_data, file_name=f"empenho_{val_num}.pdf", mime='application/pdf', key=f"btn_pdf_edit_{dados_edicao['id']}")

        with st.container(border=True):
            ce1, ce2, ce3 = st.columns(3)
            e_prog = ce1.selectbox("Programa", options=lista_programas, index=prog_index, key="form_prog")
            e_num = ce2.text_input("Nº Empenho", value=val_num, key="form_num")
            e_data = ce3.date_input("Data do Empenho", value=val_data, format="DD/MM/YYYY", key="form_data")
            
            ce4, ce5, ce6 = st.columns(3)
            e_ob = ce4.text_input("Ordem Bancária (OB)", value=val_ob, key="form_ob")
            e_data_ob = ce5.date_input("Data da OB", value=val_data_ob, format="DD/MM/YYYY", key="form_data_ob")
            e_valor = ce6.number_input("Valor (R$)", value=val_valor, min_value=0.0, step=0.01, format="%.2f", key="form_valor")
            
            ce7, ce8, ce9 = st.columns(3)
            status_opts = ["EXECUTADO", "PENDENTE", "CANCELADO"]
            try:
                status_idx = status_opts.index(val_status)
            except ValueError:
                status_idx = 1
                
            e_status = ce7.selectbox("Status", status_opts, index=status_idx, key="form_status")
            e_data_nf = None
            if e_status == "EXECUTADO":
                e_data_nf = ce8.date_input("Data Nota Fiscal", value=val_data_nf, format="DD/MM/YYYY", key="form_data_nf")
            else: ce8.write("---")
            e_obs = ce9.text_input("Observação", value=val_obs, key="form_obs")
            e_itens = st.text_area("Itens Comprados / Descrição", value=val_itens, height=100, key="form_itens")

            st.markdown("---")
            st.subheader("📎 Anexos (Opcionais - Máx 2MB cada)")
            
            # --- 3 COLUNAS PARA ANEXOS ---
            col_file1, col_file2, col_file3 = st.columns(3)
            
            with col_file1:
                st.markdown("**📄 Arquivo do Empenho**")
                
                # Suporte ao arquivo antigo (file_data) ou novo (emp_data)
                emp_b64 = current_files.get('emp_data') or current_files.get('file_data')
                emp_nm = current_files.get('emp_name') or current_files.get('file_name', 'empenho.pdf')
                
                if emp_b64:
                    st.markdown(f"<div class='download-box'>Arquivo atual:<br><b>{emp_nm}</b></div>", unsafe_allow_html=True)
                    try:
                        bin_emp = base64.b64decode(emp_b64)
                        st.download_button("⬇️ Baixar Empenho", data=bin_emp, file_name=emp_nm, key="dl_emp")
                    except: st.error("Erro no download.")
                
                e_file_emp = st.file_uploader("Enviar Documento do Empenho", type=["pdf", "jpg", "png", "jpeg"], key="up_emp")

            with col_file2:
                st.markdown("**📁 Nota Fiscal**")
                if current_files.get('nf_data'):
                    st.markdown(f"<div class='download-box'>Arquivo atual:<br><b>{current_files.get('nf_name', 'nf.pdf')}</b></div>", unsafe_allow_html=True)
                    try:
                        bin_nf = base64.b64decode(current_files.get('nf_data'))
                        st.download_button("⬇️ Baixar Nota Fiscal", data=bin_nf, file_name=current_files.get('nf_name', 'nf.pdf'), key="dl_nf")
                    except: st.error("Erro no download.")
                
                e_file_nf = st.file_uploader("Enviar Nota Fiscal", type=["pdf", "jpg", "png", "jpeg"], key="up_nf")

            with col_file3:
                st.markdown("**📂 Comprovante de Pagamento**")
                if current_files.get('comp_data'):
                    st.markdown(f"<div class='download-box'>Arquivo atual:<br><b>{current_files.get('comp_name', 'recibo.pdf')}</b></div>", unsafe_allow_html=True)
                    try:
                        bin_comp = base64.b64decode(current_files.get('comp_data'))
                        st.download_button("⬇️ Baixar Comprovante", data=bin_comp, file_name=current_files.get('comp_name', 'recibo.pdf'), key="dl_comp")
                    except: st.error("Erro no download.")
                
                e_file_comp = st.file_uploader("Enviar Comprovante", type=["pdf", "jpg", "png", "jpeg"], key="up_comp")

            st.markdown("---")

            c_act1, c_act2, c_act3 = st.columns([1, 1, 4])
            
            def run_save():
                if not e_data:
                    st.error("⚠️ A Data do Empenho é obrigatória!")
                    return
                # Deixei bem claro que é a DATA que é obrigatória, não o arquivo.
                if e_status == "EXECUTADO" and not e_data_nf:
                    st.error("⚠️ Para o status EXECUTADO, preencha o campo 'Data Nota Fiscal' acima.")
                    return

                str_d_emp = e_data.strftime("%Y-%m-%d")
                str_d_ob = e_data_ob.strftime("%Y-%m-%d") if e_data_ob else ""
                str_d_nf = e_data_nf.strftime("%Y-%m-%d") if e_data_nf else ""

                payload = {
                    "programa": e_prog, "numero_empenho": e_num, "data_empenho": str_d_emp,
                    "ordem_bancaria": e_ob, "data_ob": str_d_ob, "valor": e_valor,
                    "data_nota_fiscal": str_d_nf, "status": e_status, "itens": e_itens, "observacao": e_obs
                }

                target_id = dados_edicao.get('id') if is_edit_mode else str(datetime.now().timestamp())
                
                save_files_to_firebase(st.session_state['db_conn'], target_id, e_file_emp, e_file_nf, e_file_comp)
                
                has_any_file = False
                if e_file_emp or e_file_nf or e_file_comp: 
                    has_any_file = True
                elif is_edit_mode and (current_files.get('emp_data') or current_files.get('file_data') or current_files.get('nf_data') or current_files.get('comp_data')): 
                    has_any_file = True
                
                payload['has_file'] = has_any_file 

                if is_edit_mode:
                    idx = -1
                    for i, e in enumerate(st.session_state['empenhos_global']):
                        if e.get('id') == target_id:
                            idx = i
                            break
                    if idx != -1:
                        st.session_state['empenhos_global'][idx].update(payload)
                else:
                    payload['id'] = target_id
                    st.session_state['empenhos_global'].append(payload)
                
                save_empenhos_to_firebase(st.session_state['db_conn'], st.session_state['empenhos_global'])
                st.success("Salvo com sucesso!")
                st.session_state['empenho_mode'] = 'list'
                st.rerun()

            if c_act1.button("💾 Salvar", type="primary"): run_save()
            if c_act2.button("❌ Cancelar"):
                st.session_state['empenho_mode'] = 'list'
                st.rerun()
            if is_edit_mode:
                with c_act3:
                    with st.popover("🗑️ Excluir"):
                        st.write("Tem certeza que deseja excluir permanentemente?")
                        if st.button("Sim, excluir"):
                            t_id = dados_edicao.get('id')
                            st.session_state['empenhos_global'] = [e for e in st.session_state['empenhos_global'] if e.get('id') != t_id]
                            delete_file_from_firebase(st.session_state['db_conn'], t_id)
                            save_empenhos_to_firebase(st.session_state['db_conn'], st.session_state['empenhos_global'])
                            st.success("Registro excluído!")
                            st.session_state['empenho_mode'] = 'list'
                            st.rerun()

# --- FUNÇÃO PRINCIPAL ---
def main():
    try:
        init_session_state()

        modulo, conta = sidebar_config()

        st.title("🏫 Gestão Financeira Escolar")

        if modulo == "🏦 Movimentação Financeira":
            if conta:
                st.header(f"📂 Conta: {conta}")
                
                anos = sorted(st.session_state['available_years'])
                default_ix = len(anos) - 1 if anos else 0
                if anos:
                    ano_atual = st.selectbox("📅 Exercício (Ano):", anos, index=default_ix)
                else:
                    ano_atual = datetime.now().year
                    st.info(f"Usando ano atual: {ano_atual} (Crie exercícios na barra lateral)")

                dados_conta = st.session_state['accounts'][conta]
                programas = dados_conta.get('programas', [])

                with st.expander("⚙️ Gerenciar Programas da Conta"):
                    c1, c2 = st.columns([3, 1])
                    novo_p = c1.text_input("Novo Programa", key=f"novo_p_{conta}")
                    if c2.button("Adicionar", key=f"btn_add_{conta}"):
                        if novo_p and novo_p not in programas:
                            programas.append(novo_p)
                            st.session_state['accounts'][conta]['programas'] = programas
                            save_account_to_firebase(st.session_state['db_conn'], conta, st.session_state['accounts'][conta])
                            st.rerun()
                        elif novo_p:
                            st.warning("Programa já existe.")

                    st.divider()
                    st.markdown("#### Programas Ativos:")
                    for p_idx, p_name in enumerate(programas):
                        cp1, cp2 = st.columns([4, 1])
                        cp1.markdown(f"📌 **{p_name}**")
                        if cp2.button("🗑️", key=f"del_prog_{conta}_{p_idx}"):
                            programas.pop(p_idx)
                            st.session_state['accounts'][conta]['programas'] = programas
                            save_account_to_firebase(st.session_state['db_conn'], conta, st.session_state['accounts'][conta])
                            st.rerun()
                    
                    st.divider()
                    st.markdown(f"#### 💰 Saldo Inicial / Anterior para {ano_atual}")
                    st.caption(f"Defina aqui o saldo de abertura especificamente para o ano de {ano_atual}. Isso não afetará outros anos.")
                    
                    if 'saldos_anuais' not in dados_conta:
                        dados_conta['saldos_anuais'] = {}
                    str_ano = str(ano_atual)
                    if str_ano not in dados_conta['saldos_anuais']:
                        dados_conta['saldos_anuais'][str_ano] = {}
                    
                    saldos_mudaram = False
                    for p_name in programas:
                        vals_atuais = dados_conta['saldos_anuais'][str_ano].get(p_name, {'Capital': 0.0, 'Custeio': 0.0})
                        
                        st.markdown(f"**📂 {p_name}**")
                        c_scap, c_scust = st.columns(2)
                        
                        novo_cap = c_scap.number_input(f"Saldo Anterior Capital ({ano_atual})", value=float(vals_atuais.get('Capital', 0.0)), key=f"sa_cap_{conta}_{ano_atual}_{p_name}")
                        novo_cust = c_scust.number_input(f"Saldo Anterior Custeio ({ano_atual})", value=float(vals_atuais.get('Custeio', 0.0)), key=f"sa_cust_{conta}_{ano_atual}_{p_name}")
                        
                        if novo_cap != vals_atuais.get('Capital', 0.0) or novo_cust != vals_atuais.get('Custeio', 0.0):
                            dados_conta['saldos_anuais'][str_ano][p_name] = {'Capital': novo_cap, 'Custeio': novo_cust}
                            saldos_mudaram = True

                    if saldos_mudaram:
                        if st.button(f"💾 Salvar Saldos de {ano_atual}", key=f"save_saldos_{conta}_{ano_atual}"):
                            save_account_to_firebase(st.session_state['db_conn'], conta, dados_conta)
                            st.success(f"Saldos de {ano_atual} atualizados!")
                            st.rerun()

                if programas:
                    render_financeiro_view(conta, ano_atual, programas)
                else:
                    st.warning("⚠️ Cadastre pelo menos um programa acima para iniciar os lançamentos.")
            else:
                st.info("👈 Selecione uma conta existente ou crie uma nova na barra lateral para começar.")

        elif modulo == "📜 Controle de Empenhos":
            render_empenhos_global_view()

        elif modulo == "📈 Resumo Consolidado":
            render_resumo_consolidado_view()

    except Exception as e:
        st.error(f"Ocorreu um erro no sistema: {e}")

if __name__ == "__main__":
    main()