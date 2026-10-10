import type { CatalogueItem } from '../types/ktru'

export const mockCatalogue: CatalogueItem[] = [
  {
    id: 'hammer-carpentry', code: '25.73.30.141-00000010', name: 'Молоток', category: 'tools',
    okpd2: { code: '25.73.30.141', name: 'Молотки' },
    unit: { name: 'Штука', symbol: 'шт' }, positionType: 'non-aggregated',
    additionalCharacteristicsAllowed: true,
    characteristics: [
      { name: 'Тип', allowedValues: ['Столярный'], required: true },
      { name: 'Масса молотка', allowedValues: [0.1, 0.2, 0.4, 0.6, 0.8, 1, 1.2, 1.4, 1.6, 1.8, 2, 2.25, 2.5], unit: { name: 'Килограмм', symbol: 'кг' }, required: true },
      { name: 'Материал бойка', allowedValues: ['Сталь', 'Алюминий', 'Медь'], required: true },
      { name: 'Безынерционный', allowedValues: ['Нет', 'Да'], required: true },
      { name: 'Форма бойка', allowedValues: ['Квадратный', 'Клиновидный', 'Круглый'], required: true },
      { name: 'Длина рукоятки', allowedValues: [100, 150, 200, 300, 400, 500, 600, 700, 800, 900], unit: { name: 'Миллиметр', symbol: 'мм' }, required: true },
    ],
  },
  {
    id: 'office-chair-demo', code: 'ДЕМО-МЕБЕЛЬ-001', name: 'Кресло офисное', category: 'furniture',
    okpd2: { code: '31.01.11.150', name: 'Мебель для сидения' },
    unit: { name: 'Штука', symbol: 'шт' }, positionType: 'non-aggregated',
    additionalCharacteristicsAllowed: true,
    characteristics: [
      { name: 'Назначение', allowedValues: ['Для руководителя', 'Для персонала', 'Для посетителей'], required: true },
      { name: 'Подлокотники', allowedValues: ['Да', 'Нет'], required: true },
      { name: 'Регулировка высоты', allowedValues: ['Да', 'Нет'], required: true },
    ],
  },
  {
    id: 'protective-jacket-demo', code: 'ДЕМО-ОДЕЖДА-001', name: 'Куртка специальная', category: 'clothing',
    okpd2: { code: '14.12.30.120', name: 'Одежда производственная и профессиональная' },
    unit: { name: 'Штука', symbol: 'шт' }, positionType: 'non-aggregated',
    additionalCharacteristicsAllowed: true,
    characteristics: [
      { name: 'Сезон', allowedValues: ['Зима', 'Демисезон'], required: true },
      { name: 'Пол', allowedValues: ['Мужской', 'Женский', 'Универсальный'], required: true },
      { name: 'Размер', allowedValues: ['44–46', '48–50', '52–54', '56–58'], required: true },
    ],
  },
  {
    id: 'adjustable-wrench-demo', code: 'ДЕМО-ИНСТРУМЕНТ-002', name: 'Ключ гаечный', category: 'tools',
    okpd2: { code: '25.73.30.171', name: 'Ключи гаечные ручные' },
    unit: { name: 'Штука', symbol: 'шт' }, positionType: 'non-aggregated',
    additionalCharacteristicsAllowed: true,
    characteristics: [
      { name: 'Тип', allowedValues: ['Разводной', 'Рожковый', 'Накидной'], required: true },
      { name: 'Длина', allowedValues: [150, 200, 250, 300], unit: { name: 'Миллиметр', symbol: 'мм' }, required: true },
    ],
  },
  {
    id: 'document-cabinet-demo', code: 'ДЕМО-МЕБЕЛЬ-002', name: 'Шкаф офисный', category: 'furniture',
    okpd2: { code: '31.01.11.120', name: 'Мебель деревянная для офисов' },
    unit: { name: 'Штука', symbol: 'шт' }, positionType: 'non-aggregated',
    additionalCharacteristicsAllowed: true,
    characteristics: [
      { name: 'Назначение', allowedValues: ['Для документов', 'Для одежды'], required: true },
      { name: 'Тип дверей', allowedValues: ['Распашные', 'Раздвижные'], required: true },
      { name: 'Количество секций', allowedValues: [1, 2, 3, 4], required: true },
    ],
  },
  {
    id: 'signal-vest-demo', code: 'ДЕМО-ОДЕЖДА-002', name: 'Жилет сигнальный', category: 'clothing',
    okpd2: { code: '14.12.30.131', name: 'Жилеты производственные и профессиональные' },
    unit: { name: 'Штука', symbol: 'шт' }, positionType: 'non-aggregated',
    additionalCharacteristicsAllowed: true,
    characteristics: [
      { name: 'Цвет', allowedValues: ['Флуоресцентный жёлтый', 'Флуоресцентный оранжевый'], required: true },
      { name: 'Класс видимости', allowedValues: [1, 2, 3], required: true },
      { name: 'Размер', allowedValues: ['M', 'L', 'XL', 'XXL'], required: true },
    ],
  },
]
