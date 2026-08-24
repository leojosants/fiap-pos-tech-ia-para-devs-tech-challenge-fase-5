"""Gerador determinístico da base simulada de imóveis do CasaLead.

Produz data/seed/properties.json com 60 imóveis coerentes entre si:
preço derivado do m² real do bairro, aluguel derivado do preço de venda
por yield de mercado, e área compatível com a quantidade de quartos.

O seed fixo garante que a base seja idêntica em qualquer execução,
tornando a demonstração reprodutível e os testes estáveis.

Uso:
    uv run python scripts/generate_properties.py
"""

import json
import random
from dataclasses import asdict
from pathlib import Path

from src.core.enums import InvestorProfile, Operation, PropertyType, Zone
from src.core.models import Property

SEED = 369985          # RM do autor — arbitrário, porém rastreável
TOTAL_IMOVEIS = 60
SAIDA = Path("data/seed/properties.json")


# ============================================================
# PARÂMETROS DE MERCADO POR BAIRRO
# ============================================================

BAIRROS = {
    "Moema":         {"zona": Zone.SUL,    "m2": (13000, 17000), "valorizacao": (6.0, 8.5)},
    "Vila Olímpia":  {"zona": Zone.SUL,    "m2": (14000, 18500), "valorizacao": (6.5, 9.0)},
    "Saúde":         {"zona": Zone.SUL,    "m2": (8500, 11000),  "valorizacao": (5.0, 7.0)},
    "Pinheiros":     {"zona": Zone.OESTE,  "m2": (13000, 17500), "valorizacao": (7.0, 9.5)},
    "Butantã":       {"zona": Zone.OESTE,  "m2": (8000, 10500),  "valorizacao": (4.5, 6.5)},
    "Bela Vista":    {"zona": Zone.CENTRO, "m2": (7500, 10000),  "valorizacao": (4.0, 6.0)},
    "Santa Cecília": {"zona": Zone.CENTRO, "m2": (8000, 11000),  "valorizacao": (5.5, 8.0)},
    "Santana":       {"zona": Zone.NORTE,  "m2": (7000, 9500),   "valorizacao": (4.0, 6.0)},
    "Tucuruvi":      {"zona": Zone.NORTE,  "m2": (6500, 8800),   "valorizacao": (4.5, 6.5)},
}

# Agrupa bairros por zona — garante distribuição equilibrada entre as
# quatro zonas, independentemente de quantos bairros cada uma possui.
BAIRROS_POR_ZONA: dict[Zone, list[str]] = {}
for _nome, _params in BAIRROS.items():
    BAIRROS_POR_ZONA.setdefault(_params["zona"], []).append(_nome)

# Distribuição de tipos: (tipo, peso relativo)
DISTRIBUICAO_TIPOS = [
    (PropertyType.APARTAMENTO, 60),
    (PropertyType.CASA, 15),
    (PropertyType.STUDIO, 15),
    (PropertyType.SALA_COMERCIAL, 10),
]

# Faixa de área útil (m²) por tipo e quantidade de quartos
AREAS = {
    PropertyType.STUDIO: {0: (22, 38)},
    PropertyType.APARTAMENTO: {1: (35, 50), 2: (48, 75), 3: (68, 110), 4: (100, 165)},
    PropertyType.CASA: {2: (70, 110), 3: (100, 180), 4: (150, 280)},
    PropertyType.SALA_COMERCIAL: {0: (28, 90)},
}

CARACTERISTICAS_RESIDENCIAIS = [
    "portaria 24h", "elevador", "sacada", "churrasqueira", "piscina",
    "academia", "playground", "salão de festas", "área verde",
    "próximo ao metrô", "reformado", "andar alto", "vista livre",
    "cozinha planejada", "armários embutidos", "silencioso",
    "próximo a parque", "coworking no prédio", "bicicletário",
    "ensolarado", "pet friendly", "segurança 24h",
]

CARACTERISTICAS_COMERCIAIS = [
    "ar-condicionado central", "recepção", "estacionamento rotativo",
    "próximo ao metrô", "piso elevado", "copa", "sala de reunião",
    "portaria 24h", "prédio corporativo", "fachada de vidro",
]

RUAS = [
    "Rua das Acácias", "Avenida dos Ipês", "Rua Doutor Alceu",
    "Alameda dos Jacarandás", "Rua Coronel Bento", "Avenida Vereador Silva",
    "Rua Padre Antônio", "Travessa São Bento", "Rua Barão de Itu",
    "Avenida Professor Lima", "Rua Marechal Deodoro", "Rua Sete de Abril",
]


# ============================================================
# GERAÇÃO
# ============================================================

def _sortear_tipo(rng: random.Random) -> PropertyType:
    """Sorteia o tipo do imóvel respeitando a distribuição definida."""
    tipos, pesos = zip(*DISTRIBUICAO_TIPOS)
    return rng.choices(tipos, weights=pesos, k=1)[0]


def _sortear_quartos(rng: random.Random, tipo: PropertyType) -> int:
    """Define a quantidade de quartos compatível com o tipo."""
    opcoes = list(AREAS[tipo].keys())
    if tipo == PropertyType.APARTAMENTO:
        return rng.choices(opcoes, weights=[15, 40, 33, 12], k=1)[0]
    if tipo == PropertyType.CASA:
        return rng.choices(opcoes, weights=[30, 45, 25], k=1)[0]
    return opcoes[0]


def _montar_descricao(
    tipo: PropertyType, bairro: str, quartos: int,
    area: float, caracteristicas: list[str], rng: random.Random,
) -> str:
    """Compõe a descrição em texto livre — insumo da busca semântica."""
    if tipo == PropertyType.SALA_COMERCIAL:
        base = (
            f"Sala comercial de {area:.0f}m² em {bairro}, "
            f"ideal para escritórios e consultórios."
        )
    elif tipo == PropertyType.STUDIO:
        base = (
            f"Studio compacto e funcional de {area:.0f}m² em {bairro}, "
            f"perfeito para quem mora sozinho ou busca praticidade."
        )
    else:
        nome_tipo = "Apartamento" if tipo == PropertyType.APARTAMENTO else "Casa"
        base = (
            f"{nome_tipo} de {quartos} quarto{'s' if quartos > 1 else ''} "
            f"com {area:.0f}m² em {bairro}."
        )

    destaques = rng.sample(caracteristicas, k=min(3, len(caracteristicas)))
    complemento = f" Destaques: {', '.join(destaques)}."

    fechos = [
        " Excelente localização, próximo a comércio e transporte público.",
        " Região tranquila e bem servida de serviços.",
        " Ótima oportunidade para quem busca qualidade de vida na capital.",
        " Imóvel pronto para morar, com documentação regularizada.",
        " Bairro em franca valorização, com alta demanda locatícia.",
    ]
    return base + complemento + rng.choice(fechos)


def gerar_imoveis(quantidade: int = TOTAL_IMOVEIS) -> list[Property]:
    """Gera a lista completa de imóveis sintéticos."""
    rng = random.Random(SEED)
    imoveis: list[Property] = []
    zonas = list(BAIRROS_POR_ZONA.keys())

    for i in range(1, quantidade + 1):
        zona = zonas[i % len(zonas)]
        bairros_da_zona = BAIRROS_POR_ZONA[zona]
        bairro = bairros_da_zona[(i // len(zonas)) % len(bairros_da_zona)]
        params = BAIRROS[bairro]
        tipo = _sortear_tipo(rng)
        quartos = _sortear_quartos(rng, tipo)

        area_min, area_max = AREAS[tipo][quartos]
        area = round(rng.uniform(area_min, area_max), 1)

        # Preço de venda derivado do m² do bairro
        preco_m2 = rng.uniform(*params["m2"])
        if tipo == PropertyType.CASA:
            preco_m2 *= 0.85          # casas custam menos por m² que apartamentos
        elif tipo == PropertyType.SALA_COMERCIAL:
            preco_m2 *= 0.90
        preco_venda = round(area * preco_m2, -3)   # arredonda ao milhar

        # Aluguel derivado do valor de venda por yield mensal de mercado
        yield_mensal = rng.uniform(0.0035, 0.0055)
        preco_aluguel = round(preco_venda * yield_mensal, -1)

        # Operação disponível
        operacao = rng.choices(
            [Operation.VENDA, Operation.ALUGUEL, Operation.AMBOS],
            weights=[45, 20, 35], k=1,
        )[0]

        # Rentabilidade anual bruta — coerente com o yield sorteado
        rentabilidade = round(yield_mensal * 12 * 100, 2)
        valorizacao = round(rng.uniform(*params["valorizacao"]), 1)

        # Perfil de investimento derivado dos indicadores
        if rentabilidade >= 6.0 and valorizacao < 6.5:
            perfil = InvestorProfile.CONSERVADOR
        elif valorizacao >= 7.5:
            perfil = InvestorProfile.ARROJADO
        else:
            perfil = InvestorProfile.MODERADO

        comercial = tipo == PropertyType.SALA_COMERCIAL
        pool = CARACTERISTICAS_COMERCIAIS if comercial else CARACTERISTICAS_RESIDENCIAIS
        caracteristicas = rng.sample(pool, k=rng.randint(3, 6))

        suites = 0 if quartos == 0 else rng.randint(0, min(quartos, 2))
        banheiros = max(1, quartos) if quartos else 1
        vagas = 0 if tipo == PropertyType.STUDIO else rng.randint(0, min(quartos + 1, 3))
        andar = None if tipo == PropertyType.CASA else rng.randint(1, 22)

        titulo_tipo = {
            PropertyType.APARTAMENTO: f"Apartamento {quartos} quartos",
            PropertyType.CASA: f"Casa {quartos} quartos",
            PropertyType.STUDIO: "Studio",
            PropertyType.SALA_COMERCIAL: "Sala comercial",
        }[tipo]

        imovel = Property(
            id=i,
            codigo=f"CL{i:04d}",
            titulo=f"{titulo_tipo} — {bairro}",
            tipo=tipo,
            operacao=operacao,
            zona=params["zona"],
            bairro=bairro,
            endereco_aproximado=f"{rng.choice(RUAS)}, {bairro}",
            preco_venda=preco_venda if operacao != Operation.ALUGUEL else None,
            preco_aluguel=preco_aluguel if operacao != Operation.VENDA else None,
            condominio=round(rng.uniform(350, 1800), -1) if tipo != PropertyType.CASA else 0.0,
            iptu=round(preco_venda * rng.uniform(0.006, 0.011), -1),
            quartos=quartos,
            suites=suites,
            banheiros=banheiros,
            vagas=vagas,
            area_util=area,
            andar=andar,
            ano_construcao=rng.randint(1985, 2024),
            mobiliado=rng.random() < 0.22,
            aceita_pet=rng.random() < 0.78,
            caracteristicas=caracteristicas,
            descricao=_montar_descricao(tipo, bairro, quartos, area, caracteristicas, rng),
            rentabilidade_estimada=rentabilidade,
            potencial_valorizacao=valorizacao,
            perfil_investimento=perfil,
        )
        imoveis.append(imovel)

    return imoveis


def main() -> None:
    """Gera a base e grava o arquivo JSON versionado."""
    imoveis = gerar_imoveis()
    SAIDA.parent.mkdir(parents=True, exist_ok=True)

    dados = [asdict(imovel) for imovel in imoveis]
    SAIDA.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"✓ {len(imoveis)} imóveis gerados em {SAIDA}")
    print("\nDistribuição por zona:")
    for zona in Zone:
        total = sum(1 for im in imoveis if im.zona == zona)
        print(f"  {zona.value:8s} {total:3d}")

    print("\nDistribuição por tipo:")
    for tipo in PropertyType:
        total = sum(1 for im in imoveis if im.tipo == tipo)
        print(f"  {tipo.value:16s} {total:3d}")

    vendas = [im.preco_venda for im in imoveis if im.preco_venda]
    print(f"\nPreço de venda: R$ {min(vendas):,.0f} a R$ {max(vendas):,.0f}")

    alugueis = [im.preco_aluguel for im in imoveis if im.preco_aluguel]
    print(f"Aluguel:        R$ {min(alugueis):,.0f} a R$ {max(alugueis):,.0f}")


if __name__ == "__main__":
    main()