import google.generativeai as genai

CHAVE = "AIzaSyAGmtBsUCHnedh5jGQkUVKuSWc4jBYBh7k" # Use sua chave atual
genai.configure(api_key=CHAVE)

try:
    # Teste simples apenas com texto (sem imagem) para validar a conexão
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("Olá, você está funcionando?")
    print("-" * 30)
    print("SUCESSO!")
    print("Resposta do Gemini:", response.text)
    print("-" * 30)
except Exception as e:
    print("-" * 30)
    print("ERRO DETECTADO:")
    print(e)
    print("-" * 30)