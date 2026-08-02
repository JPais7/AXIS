# Reproduzir o estudo computacional DDX24

Este pacote reconstrói, sem acesso à Internet:

1. a meta-análise primária de DDX24 em GSE194315 e GSE288581;
2. a análise de sensibilidade que acrescenta GSE163314 como CD8 geral;
3. as verificações de integridade e as regras científicas do estudo.

## Execução

Na raiz do projeto:

```powershell
.\.venv\Scripts\axis.exe reproduce ddx24-study
```

Resultados:

```text
data/reproducibility/ddx24-study/
├── checks.tsv
├── reproduction-report.json
└── rebuilt/
    ├── primary-cd8/
    └── broad-cd8-sensitivity.json
```

O comando falha se:

- um ficheiro estiver ausente ou tiver um SHA-256 diferente;
- o `poetry.lock` tiver mudado sem atualização explícita do manifesto;
- participantes deixarem de ser a unidade estatística;
- uma coorte for contada duas vezes;
- HRA001027 entrar na síntese primária;
- GSE163314 deixar de estar marcado como sensibilidade;
- os resultados deixarem de corresponder aos valores congelados.

## Atualização deliberada

Alterações legítimas aos dados, ambiente ou método exigem:

1. uma nova versão do estudo;
2. justificação científica;
3. regeneração dos valores esperados;
4. atualização explícita dos hashes;
5. revisão dos testes e do manuscrito.

Nunca atualize o manifesto apenas para fazer uma verificação falhada passar.
