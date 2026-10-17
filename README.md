# CAVE (KV) — Assistente Pessoal de IA para Desktop

O CAVE (**KV**) é um assistente pessoal modular controlado por voz para **Windows 10/11**, acompanhado de uma interface web móvel para **Android / smartphones** via Wi-Fi local. Ele suporta **Português do Brasil (`pt-BR`)** como idioma principal de fala, mantendo o código-fonte, a arquitetura e a documentação técnica em inglês.

---

## 1. Principais Recursos

1. **Ativação Contínua sem Botão (`"Cave"` / `"KV"`)**:
* O microfone fica ativo em segundo plano no modo de espera, ignorando conversas comuns até detectar a palavra de ativação `"Cave"` ou `"KV"`.
* Permite comandos diretos na mesma frase (*"Cave, abrir o Chrome"*) ou uma janela de sessão ativa (padrão de 8 segundos) para comandos seguidos.
* Suprime reconhecimentos duplicados e silencia o microfone enquanto o assistente fala (TTS) para evitar loops de eco acústico.


2. **Smartphone como Microfone e Controle Remoto**:
* Aplicativo web móvel responsivo (`/mobile`) via rede Wi-Fi local com suporte a `HTTPS` e `WSS`.
* Transmite áudio PCM mono de 16 kHz e eventos de reconhecimento de fala do navegador para o PC Windows.
* Inclui pareamento por PIN, monitoramento de batimento cardíaco (*heartbeat*), reconexão automática, bloqueio de tela ativo (*Screen Wake Lock*) e botão de parada de emergência.


3. **Controle Completo de Aplicativos no Windows**:
* Abre aplicativos registrados (`Chrome`, `VS Code`, `Steam`, `Discord`, `Spotify`, `Explorador de Arquivos`, `Downloads`, `Configurações`, `Gerenciador de Tarefas`, `Terminal`, `Bloco de Notas`, `Calculadora`) e atalhos customizados do usuário por meio de listas seguras de executáveis.
* Verifica se o aplicativo já está em execução para evitar abrir duplicatas indesejadas.


4. **Ditado de Texto em Linguagem Natural**:
* Suporta ditado rápido em linha (*"Cave, digite Olá, tudo bem?"*) e Modo Ditado contínuo (*"Cave, ativar modo ditado"* ... `"parar ditado"`).
* Converte pontuações faladas (*"vírgula"*, `"ponto final"*, `"ponto de interrogação"*, `"novo parágrafo"`) e preserva o conteúdo anterior da área de transferência do Windows após colar textos com acentuação em português.


5. **Controle de Teclado, Mouse e Modo Jogo (WASD Simultâneo)**:
* Utiliza códigos de varredura de hardware Win32 (`SendInput` + `KEYEVENTF_SCANCODE`) para manter teclas pressionadas simultaneamente (*W + D*, *W + A*, *W + Shift*).
* Inclui um *watchdog* de segurança de 200 ms que libera automaticamente teclas pressionadas ao sair do modo jogo, expirar o tempo limite, perder a conexão móvel ou ao comando *"Cave, pare tudo"*.



---

## 2. Estrutura Completa de Pastas e Arquivos

```text
CAVE/
├── main.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
├── config/
│   ├── settings.json
│   ├── applications.json
│   ├── commands.json
│   └── paired_devices.json (gerado automaticamente)
├── cave/
│   ├── __init__.py
│   ├── assistant.py
│   ├── state_manager.py
│   ├── wake_word.py
│   ├── audio_capture.py
│   ├── speech_recognition.py
│   ├── intent_engine.py
│   ├── command_registry.py
│   ├── command_dispatcher.py
│   ├── application_manager.py
│   ├── text_dictation.py
│   ├── keyboard_controller.py
│   ├── mouse_controller.py
│   ├── game_controller.py
│   ├── speech_output.py
│   ├── security.py
│   ├── logging_config.py
│   └── ai_assistant.py
├── server/
│   ├── __init__.py
│   ├── app.py
│   ├── routes.py
│   ├── websocket_handlers.py
│   ├── authentication.py
│   └── tls.py
├── templates/
│   ├── mobile.html
│   └── dashboard.html
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   ├── mobile.js
│   │   └── dashboard.js
│   └── assets/
│       └── logo.svg
├── models/
│   └── vosk-model-small-pt-0.3/ (modelo offline pt-BR)
└── tests/
    ├── test_wake_word.py
    ├── test_intent_engine.py
    ├── test_command_registry.py
    ├── test_dictation.py
    ├── test_game_controller.py
    └── test_security.py

```

---

## 3. Guia de Instalação e Execução no Windows

### Pré-requisitos

* **Sistema Operacional**: Windows 10 ou Windows 11 (64 bits).
* **Python**: Python **3.11** ou **3.12** instalado.
* **Rede**: PC Windows e Smartphone conectados à **mesma rede Wi-Fi local**.

### Passo a Passo

1. Abra o **PowerShell** e clone o repositório:
```powershell
git clone https://github.com/realleokv/kv_controller_v1.git
cd kv_controller_v1

```


2. Crie e ative o ambiente virtual:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

```


3. Instale as dependências:
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt

```


4. Baixe o modelo de reconhecimento de voz offline `pt-BR` (Vosk):
```powershell
New-Item -ItemType Directory -Force -Path models
Invoke-WebRequest -Uri "https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip" -OutFile "models\vosk-pt.zip"
Expand-Archive -Path "models\vosk-pt.zip" -DestinationPath "models" -Force
Remove-Item "models\vosk-pt.zip"

```


5. Configure o arquivo de ambiente:
```powershell
Copy-Item .env.example .env

```


6. Execute os testes automatizados para verificar o sistema:
```powershell
pytest -v

```


7. Inicie o assistente CAVE:
```powershell
python main.py

```



---

## 4. Conectando o Smartphone

1. No seu celular Android conectado ao mesmo Wi-Fi, abra o Chrome e acesse a URL exibida no terminal do PC (ex: `[https://192.168.1.](https://192.168.1.)X:8443/mobile`).
2. Aceite o aviso de certificado autoassinado (clique em **Avançado** -> **Ir para...**).
3. Insira o **PIN de Pareamento** de 6 dígitos exibido no console do PC (padrão `482910`) e clique em **Conectar e Parear**.
4. Conceda a permissão de microfone solicitada pelo navegador.

---

## 5. Referência Rápida de Comandos de Voz

| Categoria | Exemplos de Comandos Falados (`pt-BR` / `en-US`) |
| --- | --- |
| **Ativação** | `"Cave, ..."` / `"KV, ..."` / `"Oi Cave, ..."` |
| **Aplicativos** | `"Cave, abrir o Chrome"` / `"Cave, abrir Visual Studio Code"` / `"Cave, abrir Discord"` / `"Cave, abrir Spotify"` / `"Cave, abrir o terminal"` |
| **Controle de Janelas** | `"Cave, alternar janela"` (`Alt+Tab`) / `"Cave, fechar janela atual"` (`Alt+F4` com confirmação) |
| **Ditado em Linha** | `"Cave, digite Olá vírgula tudo bem ponto de interrogação"` |
| **Modo Ditado** | `"Cave, ativar modo ditado"` -> *(fale livremente)* -> `"parar ditado"` |
| **Atalhos e Teclas** | `"Cave, pressionar Enter"` / `"Cave, selecionar tudo"` / `"Cave, copiar"` / `"Cave, colar"` / `"Cave, desfazer"` |
| **Modo Jogo (WASD)** | `"Cave, ativar modo jogo"` / `"segurar W"` / `"segurar D"` / `"segurar W e Shift"` / `"soltar W"` / `"soltar todas as teclas"` / `"desativar modo jogo"` |
| **Emergência** | `"Cave, pare tudo"` / `"Cave, stop everything"` |

---

---

# CAVE (KV) — Personal AI Desktop Assistant

CAVE (**KV**) is a modular, voice-controlled personal desktop assistant for **Windows 10/11** featuring an Android/mobile web microphone and remote control interface over local Wi-Fi. It supports **Brazilian Portuguese (`pt-BR`)** as its primary spoken language while keeping the codebase, architecture, and technical documentation in English.

---

## 1. Key Features

1. **Continuous Hands-Free Wake-Word Activation (`"Cave"` / `"KV"`)**:
* Continuously monitors audio in standby mode and ignores ordinary conversation until `"Cave"` or `"KV"` is detected.
* Supports single-utterance commands (`"Cave, open Chrome"`) as well as an active follow-up command session window (default: 8 seconds).
* Suppresses duplicate overlapping recognitions and mutes microphone capture during speech output (TTS) to prevent acoustic feedback loops.


2. **Smartphone as a Wireless Microphone & Remote Control**:
* Responsive mobile web app (`/mobile`) over local Wi-Fi supporting `HTTPS` and `WSS`.
* Streams 16 kHz mono PCM audio and browser speech recognition events to the Windows PC.
* Includes PIN pairing, session heartbeat monitoring, automatic reconnection, Screen Wake Lock integration, and an emergency stop button.


3. **Safe Windows Application Control**:
* Launches registered applications (`Chrome`, `VS Code`, `Steam`, `Discord`, `Spotify`, `File Explorer`, `Downloads`, `Settings`, `Task Manager`, `Terminal`, `Notepad`, `Calculator`) and custom user apps via allowlisted executables.
* Verifies if an application is already running to prevent launching unwanted duplicates.


4. **Natural-Language Text Dictation**:
* Supports one-shot dictation (`"Cave, type Hello, how are you?"`) and continuous Dictation Mode (`"Cave, enable dictation mode"` ... `"stop dictation"`).
* Converts spoken punctuation (`"comma"`, `"period"`, `"question mark"`, `"new paragraph"`) and preserves the user's existing Windows clipboard contents after pasting accented Portuguese text.


5. **Keyboard, Mouse & Simultaneous WASD Game Control**:
* Uses Win32 hardware scan codes (`SendInput` + `KEYEVENTF_SCANCODE`) for simultaneous key holds (`W + D`, `W + A`, `W + Shift`).
* Includes a 200 ms hardware-key safety watchdog that automatically releases held keys on mode exit, max-hold timeout, mobile disconnection, or `"Cave, stop everything"`.



---

## 2. Complete Folder and File Structure

```text
CAVE/
├── main.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
├── config/
│   ├── settings.json
│   ├── applications.json
│   ├── commands.json
│   └── paired_devices.json (auto-generated)
├── cave/
│   ├── __init__.py
│   ├── assistant.py
│   ├── state_manager.py
│   ├── wake_word.py
│   ├── audio_capture.py
│   ├── speech_recognition.py
│   ├── intent_engine.py
│   ├── command_registry.py
│   ├── command_dispatcher.py
│   ├── application_manager.py
│   ├── text_dictation.py
│   ├── keyboard_controller.py
│   ├── mouse_controller.py
│   ├── game_controller.py
│   ├── speech_output.py
│   ├── security.py
│   ├── logging_config.py
│   └── ai_assistant.py
├── server/
│   ├── __init__.py
│   ├── app.py
│   ├── routes.py
│   ├── websocket_handlers.py
│   ├── authentication.py
│   └── tls.py
├── templates/
│   ├── mobile.html
│   └── dashboard.html
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   ├── mobile.js
│   │   └── dashboard.js
│   └── assets/
│       └── logo.svg
├── models/
│   └── vosk-model-small-pt-0.3/ (offline pt-BR model)
└── tests/
    ├── test_wake_word.py
    ├── test_intent_engine.py
    ├── test_command_registry.py
    ├── test_dictation.py
    ├── test_game_controller.py
    └── test_security.py

```

---

## 3. Windows Installation & Setup Guide

### Prerequisites

* **Operating System**: Windows 10 or Windows 11 (64-bit).
* **Python**: Python **3.11** or **3.12** installed.
* **Network**: Windows PC and Smartphone connected to the **same local Wi-Fi network**.

### Step-by-Step Instructions

1. Open **PowerShell** and clone the repository:
```powershell
git clone https://github.com/realleokv/kv_controller_v1.git
cd kv_controller_v1

```


2. Create and activate the virtual environment:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

```


3. Install dependencies:
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt

```


4. Download the offline `pt-BR` speech recognition model (Vosk):
```powershell
New-Item -ItemType Directory -Force -Path models
Invoke-WebRequest -Uri "https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip" -OutFile "models\vosk-pt.zip"
Expand-Archive -Path "models\vosk-pt.zip" -DestinationPath "models" -Force
Remove-Item "models\vosk-pt.zip"

```


5. Configure the environment file:
```powershell
Copy-Item .env.example .env

```


6. Run the automated test suite to verify system integrity:
```powershell
pytest -v

```


7. Start CAVE:
```powershell
python main.py

```



---

## 4. Connecting Your Smartphone

1. On your Android phone connected to the same Wi-Fi, open Chrome and navigate to the mobile URL displayed in the PC terminal (e.g., `[https://192.168.1.](https://192.168.1.)X:8443/mobile`).
2. Accept the self-signed certificate warning (tap **Advanced** -> **Proceed to...**).
3. Enter the 6-digit **Pairing PIN** shown in the PC console (default `482910`) and tap **Connect & Pair**.
4. Grant microphone access when prompted by the browser.

---

## 5. Quick Voice Command Reference

| Category | Example Spoken Commands (`pt-BR` / `en-US`) |
| --- | --- |
| **Activation** | `"Cave, ..."` / `"KV, ..."` / `"Hey Cave, ..."` |
| **Applications** | `"Cave, open Chrome"` / `"Cave, open Visual Studio Code"` / `"Cave, open Discord"` / `"Cave, open Spotify"` / `"Cave, open the terminal"` |
| **Window Control** | `"Cave, switch to previous application"` (`Alt+Tab`) / `"Cave, close the current window"` (`Alt+F4` with confirmation) |
| **Inline Dictation** | `"Cave, type Hello, how are you question mark"` |
| **Dictation Mode** | `"Cave, enable dictation mode"` -> *(speak freely)* -> `"stop dictation"` |
| **Shortcuts & Keys** | `"Cave, press Enter"` / `"Cave, select all"` / `"Cave, copy"` / `"Cave, paste"` / `"Cave, undo"` |
| **Game Mode (WASD)** | `"Cave, enable game mode"` / `"hold W"` / `"hold D"` / `"hold W and Shift"` / `"release W"` / `"release all keys"` / `"disable game mode"` |
| **Emergency Stop** | `"Cave, stop everything"` / `"Cave, pare tudo"` |