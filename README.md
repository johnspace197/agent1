# 🔍 Streamlit + MCP + DuckDuckGo + Context7 종합 정보 검색 AI Agent

Gemini 2.5 Pro 모델을 활용한 지능형 검색 에이전트로, 웹 검색과 기술 문서 검색을 통합하여 개발자에게 최적의 정보를 제공합니다.

## ✨ 주요 기능

- **실시간 웹 검색**: DuckDuckGo를 통한 최신 정보, 뉴스, 튜토리얼 검색
- **기술 문서 검색**: Context7을 통한 공식 라이브러리 문서 및 코드 예제 검색
- **병렬 검색 처리**: 두 검색 소스를 동시에 활용하여 빠른 결과 제공
- **지능형 결과 통합**: 여러 소스의 정보를 종합하여 일관된 답변 생성
- **검색 히스토리 관리**: 이전 검색 결과를 활용한 컨텍스트 유지

## 🔧 핵심 구성 요소

### 1. 🌐 웹 검색 시스템 (DuckDuckGo MCP Server)

- **실시간 웹 검색**: 최신 정보, 뉴스, 튜토리얼 수집
- **10개 검색 결과**: 제목, URL, 요약 정보 포함
- **한국어 컨텐츠 우선**: 국내 기술 블로그 및 가이드 검색

### 2. 📚 기술 문서 검색 엔진 (Context7 MCP Server)

- **라이브러리 문서**: Python, JavaScript, React 등 공식 문서
- **100개+ 코드 스니펫**: 실행 가능한 예제 코드 포함
- **컨텍스트 검색**: 키워드 기반 지능형 문서 매칭

### 3. 🔗 MCP 통신 시스템

- **비동기 병렬 검색**: 두 MCP 서버 동시 호출
- **표준화된 프로토콜**: Model Context Protocol 준수
- **에러 핸들링**: 서버 연결 실패 시 적절한 오류 메시지

### 4. 🎈 Streamlit 웹 UI

- **실시간 검색 인터페이스**: 직관적인 채팅 UI
- **소스별 결과 구분 표시**: 검색 소스 명시
- **검색 소스 선택 옵션**: 사이드바에서 서버 상태 확인
- **접을 수 있는 섹션**: 정보 정리 및 검색 히스토리 관리

## 📋 사전 요구사항

- Python 3.8 이상
- Node.js 및 npm (MCP 서버 실행용)
- Google API Key (Gemini API 사용)

## 🚀 설치 방법

1. **저장소 클론**
```bash
git clone https://github.com/johnspace197/agent1.git
cd agent1/agent1
```

2. **의존성 설치**
```bash
pip install -r requirements.txt
```

3. **환경 변수 설정**
`.env` 파일을 생성하고 Google API Key를 설정합니다:
```
GOOGLE_API_KEY=your_api_key_here
```

4. **MCP 서버 설정 확인**
`agent.mcp.json` 파일이 올바르게 설정되어 있는지 확인합니다.

## 💻 실행 방법

```bash
streamlit run app.py
```

브라우저에서 자동으로 열리거나, 터미널에 표시된 URL(일반적으로 `http://localhost:8501`)로 접속합니다.

## 🎯 사용 방법

1. **MCP 서버 연결**
   - 사이드바에서 "Connect to MCP Servers" 버튼 클릭
   - DuckDuckGo와 Context7 서버 연결 확인

2. **검색 질문 입력**
   - 채팅 입력창에 개발 관련 질문 입력
   - 예: "Python에서 비동기 프로그래밍하는 방법은?"
   - 예: "React Hooks 사용 예제 보여줘"

3. **결과 확인**
   - 에이전트가 자동으로 웹 검색과 문서 검색을 수행
   - 통합된 답변과 검색 소스 정보 확인
   - 검색 히스토리에서 이전 검색 결과 확인 가능

## 📁 프로젝트 구조

```
agent1/
├── agent.py          # 핵심 에이전트 로직 (Gemini 모델 통합)
├── mcp_client.py     # MCP 서버 클라이언트 관리
├── app.py            # Streamlit 웹 애플리케이션
├── agent.mcp.json    # MCP 서버 설정 파일
└── requirements.txt  # Python 의존성 목록
```

## 🔑 주요 컴포넌트 설명

### Agent 클래스 (`agent.py`)
- Gemini 2.5 Pro 모델과의 통신 관리
- 검색 전략 수립 및 결과 통합
- 검색 히스토리 관리

### MCPClientManager 클래스 (`mcp_client.py`)
- DuckDuckGo 및 Context7 MCP 서버 연결 관리
- 도구 호출 및 결과 처리
- 에러 핸들링 및 재연결 로직

### Streamlit 앱 (`app.py`)
- 사용자 인터페이스 제공
- 세션 상태 관리
- 실시간 검색 결과 표시

## 🛠️ 기술 스택

- **AI 모델**: Google Gemini 2.5 Pro
- **웹 프레임워크**: Streamlit
- **검색 엔진**: DuckDuckGo, Context7
- **프로토콜**: Model Context Protocol (MCP)
- **언어**: Python 3.8+

## 📝 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.

## 🤝 기여하기

이슈 리포트나 풀 리퀘스트를 환영합니다!

## 📧 문의

프로젝트 관련 문의사항이 있으시면 이슈를 생성해주세요.

---

**Powered by Gemini 2.5 Pro, DuckDuckGo, and Context7** 🚀

