export interface DepartamentoData {
  dep: string;
  ciudades: string[];
}

export const COLOMBIA_DATA: DepartamentoData[] = [
  { dep: 'Amazonas', ciudades: ['Leticia', 'La Chorrera', 'La Pedrera', 'Puerto Nariño', 'Tarapacá', 'Puerto Santander', 'Puerto Arica', 'Puerto Alegría'] },
  {
    dep: 'Antioquia',
    ciudades: [
      'Medellín', 'Bello', 'Itagüí', 'Envigado', 'Sabaneta', 'La Estrella', 'Copacabana', 'Girardota', 'Barbosa',
      'Apartadó', 'Chigorodó', 'Carepa', 'Turbo', 'Necoclí', 'San Juan de Urabá', 'Arboletes',
      'Rionegro', 'Marinilla', 'El Carmen de Viboral', 'Guatapé', 'San Carlos', 'Granada', 'Abejorral',
      'Caucasia', 'El Bagre', 'Zaragoza', 'Segovia', 'Remedios',
      'Santa Rosa de Osos', 'Donmatías', 'Yarumal', 'Ituango', 'Valdivia', 'Tarazá',
      'Andes', 'Jericó', 'Jardín', 'Ciudad Bolívar', 'Urrao', 'Dabeiba', 'Frontino',
      'La Unión', 'Sonsón', 'Cocorná', 'San Luis', 'Puerto Triunfo',
      'Amalfi', 'Anorí', 'San Roque', 'Cisneros', 'Yolombó', 'Yalí',
    ],
  },
  { dep: 'Arauca', ciudades: ['Arauca', 'Saravena', 'Tame', 'Fortul', 'Arauquita', 'Cravo Norte', 'Puerto Rondón'] },
  {
    dep: 'Atlántico',
    ciudades: [
      'Barranquilla', 'Soledad', 'Malambo', 'Galapa', 'Sabanalarga', 'Baranoa', 'Sabanagrande',
      'Santo Tomás', 'Palmar de Varela', 'Ponedera', 'Polonuevo', 'Luruaco', 'Repelón',
      'Candelaria', 'Campo de la Cruz', 'Suan', 'Santa Lucía', 'Manatí', 'Tubará',
      'Juan de Acosta', 'Puerto Colombia', 'Piojó', 'Usiacurí',
    ],
  },
  {
    dep: 'Bogotá D.C.',
    ciudades: [
      'Bogotá', 'Usaquén', 'Chapinero', 'Santa Fe', 'San Cristóbal', 'Usme', 'Tunjuelito',
      'Bosa', 'Kennedy', 'Fontibón', 'Engativá', 'Suba', 'Barrios Unidos', 'Teusaquillo',
      'Los Mártires', 'Antonio Nariño', 'Puente Aranda', 'La Candelaria', 'Rafael Uribe Uribe',
      'Ciudad Bolívar',
    ],
  },
  {
    dep: 'Bolívar',
    ciudades: [
      'Cartagena', 'Magangué', 'El Carmen de Bolívar', 'Mompós', 'Turbaco', 'Arjona',
      'San Juan Nepomuceno', 'San Jacinto', 'Calamar', 'Villanueva', 'San Pablo', 'Simití',
      'Cantagallo', 'Morales', 'Santa Rosa del Sur', 'Pinillos', 'Hatillo de Loba',
      'Barranco de Loba', 'San Martín de Loba', 'Montecristo', 'Achí', 'Guaranda',
      'Tiquisio', 'Arenal', 'Regidor', 'Río Viejo', 'Altos del Rosario', 'San Fernando',
    ],
  },
  {
    dep: 'Boyacá',
    ciudades: [
      'Tunja', 'Duitama', 'Sogamoso', 'Chiquinquirá', 'Paipa', 'Moniquirá', 'Puerto Boyacá',
      'Villa de Leyva', 'Garagoa', 'Soatá', 'Guateque', 'Miraflores', 'Ramiriquí',
      'Tibaná', 'Jenesano', 'Nuevo Colón', 'Ventaquemada', 'Samacá', 'Boyacá',
      'Tuta', 'Cómbita', 'Motavita', 'Oicatá', 'Chivatá', 'Siachoque', 'Toca', 'Soraca',
      'Tibasosa', 'Firavitoba', 'Nobsa', 'Iza', 'Tópaga', 'Monguí', 'Corrales',
    ],
  },
  {
    dep: 'Caldas',
    ciudades: [
      'Manizales', 'Villamaría', 'Chinchiná', 'Palestina', 'Neira', 'Aranzazu', 'Salamina',
      'Aguadas', 'Pácora', 'Filadelfia', 'La Merced', 'Manzanares', 'Marquetalia', 'Marulanda',
      'Pensilvania', 'Victoria', 'Samaná', 'La Dorada', 'Norcasia', 'Supía', 'Riosucio',
      'Marmato', 'Anserma', 'Belalcázar', 'Viterbo', 'San José', 'Risaralda',
    ],
  },
  {
    dep: 'Caquetá',
    ciudades: [
      'Florencia', 'San Vicente del Caguán', 'Puerto Rico', 'El Doncello', 'El Paujil',
      'Cartagena del Chairá', 'La Montañita', 'Milán', 'Morelia', 'Albania', 'Curillo',
      'San José del Fragua', 'Belén de los Andaquíes', 'Solita', 'Solano', 'Valparaíso',
    ],
  },
  {
    dep: 'Casanare',
    ciudades: [
      'Yopal', 'Aguazul', 'Tauramena', 'Villanueva', 'Monterrey', 'Paz de Ariporo',
      'Hato Corozal', 'Trinidad', 'San Luis de Palenque', 'Orocué', 'Pore', 'Maní',
      'Nunchía', 'Chámeza', 'Recetor', 'Sabanalarga', 'Sácama', 'La Salina', 'Támara',
    ],
  },
  {
    dep: 'Cauca',
    ciudades: [
      'Popayán', 'Santander de Quilichao', 'Puerto Tejada', 'Caloto', 'Corinto', 'Miranda',
      'Buenos Aires', 'Padilla', 'Guapi', 'Timbiquí', 'López de Micay', 'Patía', 'Mercaderes',
      'La Sierra', 'Piendamó', 'Morales', 'Rosas', 'La Vega', 'Almaguer', 'Bolívar',
      'Inzá', 'Páez', 'Toribío', 'Jambaló', 'Silvia', 'Totoró', 'El Tambo', 'Cajibío', 'Timbío',
    ],
  },
  {
    dep: 'Cesar',
    ciudades: [
      'Valledupar', 'Aguachica', 'Agustín Codazzi', 'Bosconia', 'Chimichagua', 'Chiriguaná',
      'Curumaní', 'El Copey', 'El Paso', 'Gamarra', 'La Gloria', 'La Jagua de Ibirico', 'La Paz',
      'Manaure Balcón del Cesar', 'Pailitas', 'Pelaya', 'Pueblo Bello', 'Río de Oro',
      'San Alberto', 'San Diego', 'San Martín', 'Tamalameque',
    ],
  },
  {
    dep: 'Chocó',
    ciudades: [
      'Quibdó', 'Istmina', 'Tadó', 'Condoto', 'Nóvita', 'Certeguí', 'Unión Panamericana',
      'Lloró', 'Río Quito', 'Bagadó', 'El Carmen de Atrato', 'Bahía Solano', 'Nuquí',
      'Alto Baudó', 'Bajo Baudó', 'Medio Baudó', 'Riosucio', 'Unguía', 'Acandí', 'Juradó',
    ],
  },
  {
    dep: 'Córdoba',
    ciudades: [
      'Montería', 'Cereté', 'Lorica', 'Sahagún', 'Planeta Rica', 'Montelíbano', 'Puerto Libertador',
      'Ayapel', 'Chinú', 'Ciénaga de Oro', 'San Pelayo', 'San Carlos', 'San Antero',
      'San Bernardo del Viento', 'Purísima', 'Moñitos', 'Los Córdobas', 'Canalete',
      'Puerto Escondido', 'Tierralta', 'Buenavista', 'La Apartada', 'Cotorra', 'Momil', 'Pueblo Nuevo', 'Valencia',
    ],
  },
  {
    dep: 'Cundinamarca',
    ciudades: [
      'Facatativá', 'Zipaquirá', 'Soacha', 'Fusagasugá', 'Chía', 'Mosquera', 'Madrid', 'Funza',
      'Girardot', 'Tocancipá', 'Cajicá', 'Sopó', 'La Calera', 'Guasca', 'Gachancipá',
      'Sibaté', 'Anapoima', 'Apulo', 'La Mesa', 'Tocaima', 'Villeta', 'Nocaima', 'Útica',
      'Pacho', 'Tausa', 'Cogua', 'Nemocón', 'Suesca', 'Chocontá', 'Sesquilé', 'Guatavita',
      'Junín', 'Gachalá', 'Medina', 'Fómeque', 'Cáqueza', 'Chipaque', 'Une',
      'Arbeláez', 'Pasca', 'San Bernardo', 'Venecia', 'Nilo', 'Ricaurte', 'Agua de Dios', 'Viotá',
      'El Colegio', 'Cachipay', 'Zipacón', 'Bojacá', 'Subachoque', 'El Rosal',
      'Sasaima', 'Albán', 'Supatá', 'San Francisco', 'Vergara', 'La Peña', 'Nimaima',
      'Ubalá', 'Gama', 'San Juanito', 'El Calvario', 'Restrepo',
    ],
  },
  { dep: 'Guainía', ciudades: ['Inírida', 'Barrancominas', 'San Felipe', 'Puerto Colombia', 'La Guadalupe', 'Cacahual', 'Pana Pana', 'Morichal'] },
  { dep: 'Guaviare', ciudades: ['San José del Guaviare', 'Calamar', 'El Retorno', 'Miraflores'] },
  {
    dep: 'Huila',
    ciudades: [
      'Neiva', 'Pitalito', 'Garzón', 'La Plata', 'Campoalegre', 'Rivera', 'Palermo', 'Algeciras',
      'Gigante', 'Agrado', 'Tarqui', 'Saladoblanco', 'Oporapa', 'La Argentina', 'San Agustín',
      'Isnos', 'Acevedo', 'Suaza', 'Guadalupe', 'Palestina', 'Hobo', 'Iquira', 'Nataga',
      'Teruel', 'Tesalia', 'Yaguará', 'Aipe', 'Villavieja', 'Santa María', 'Baraya', 'Tello', 'Elías',
    ],
  },
  {
    dep: 'La Guajira',
    ciudades: ['Riohacha', 'Maicao', 'Uribia', 'Manaure', 'San Juan del Cesar', 'Fonseca', 'Barrancas', 'Hatonuevo', 'Distracción', 'Villanueva', 'El Molino', 'Urumita', 'La Jagua del Pilar', 'Albania'],
  },
  {
    dep: 'Magdalena',
    ciudades: [
      'Santa Marta', 'Ciénaga', 'Fundación', 'El Banco', 'Plato', 'Aracataca', 'Pivijay',
      'Salamina', 'Remolino', 'Sitionuevo', 'Zona Bananera', 'Algarrobo', 'Ariguaní', 'Chivolo',
      'El Retén', 'Guamal', 'Nueva Granada', 'Pedraza', 'Piñón', 'Puebloviejo', 'San Zenón',
      'Santa Bárbara de Pinto', 'Tenerife', 'Santa Ana', 'San Sebastián de Buenavista',
      'Concordia', 'Cerro San Antonio', 'Zapayán', 'Sabanas de San Ángel', 'Sitio Nuevo',
    ],
  },
  {
    dep: 'Meta',
    ciudades: [
      'Villavicencio', 'Acacías', 'Granada', 'Puerto López', 'Puerto Gaitán', 'San Martín',
      'Cumaral', 'Restrepo', 'El Dorado', 'El Castillo', 'Lejanías', 'Fuente de Oro',
      'San Juan de Arama', 'Mesetas', 'Vista Hermosa', 'La Macarena', 'Uribe',
      'Puerto Concordia', 'Puerto Lleras', 'Puerto Rico', 'Mapiripán', 'Barranca de Upía',
      'Cabuyaro', 'Castilla la Nueva', 'Guamal',
    ],
  },
  {
    dep: 'Nariño',
    ciudades: [
      'Pasto', 'Ipiales', 'Tumaco', 'Túquerres', 'La Unión', 'Samaniego', 'Sandoná',
      'El Charco', 'Barbacoas', 'Olaya Herrera', 'Roberto Payán', 'Francisco Pizarro', 'Mosquera',
      'Cumbal', 'Guachucal', 'Pupiales', 'Cuaspud', 'Aldana', 'Potosí', 'Sapuyes',
      'Imués', 'Funes', 'Tangua', 'El Peñol', 'Gualmatán', 'Puerres', 'Córdoba', 'Buesaco',
      'La Florida', 'Linares', 'El Rosario', 'Leiva', 'Policarpa', 'Cumbitara', 'Los Andes',
      'Colón', 'La Cruz', 'San Bernardo', 'San Pedro de Cartago', 'Belén', 'Arboleda',
      'San Pablo', 'Taminango', 'Chachagüí', 'El Tambo', 'La Llanada', 'Sotomayor',
      'Providencia', 'Ricaurte',
    ],
  },
  {
    dep: 'Norte de Santander',
    ciudades: [
      'Cúcuta', 'Ocaña', 'Pamplona', 'Villa del Rosario', 'Los Patios', 'El Zulia', 'San Cayetano',
      'Sardinata', 'Tibú', 'El Tarra', 'Teorama', 'Convención', 'Hacarí', 'San Calixto',
      'Ábrego', 'La Playa de Belén', 'Cáchira', 'Salazar', 'Santiago', 'Chitagá', 'Labateca',
      'Toledo', 'Herrán', 'Ragonvalia', 'Bochalema', 'Chinácota', 'Durania', 'Silos',
      'Cácota', 'Mutiscua', 'Pamplonita', 'Gramalote', 'Lourdes',
    ],
  },
  {
    dep: 'Putumayo',
    ciudades: [
      'Mocoa', 'Puerto Asís', 'Orito', 'Valle del Guamuez', 'Villagarzón', 'Puerto Caicedo',
      'San Miguel', 'Sibundoy', 'Colón', 'San Francisco', 'Santiago', 'Puerto Guzmán', 'Puerto Leguízamo',
    ],
  },
  {
    dep: 'Quindío',
    ciudades: ['Armenia', 'Calarcá', 'Montenegro', 'La Tebaida', 'Quimbaya', 'Circasia', 'Filandia', 'Salento', 'Buenavista', 'Córdoba', 'Génova', 'Pijao'],
  },
  {
    dep: 'Risaralda',
    ciudades: [
      'Pereira', 'Dosquebradas', 'Santa Rosa de Cabal', 'La Virginia', 'Marsella', 'Belén de Umbría',
      'Guática', 'Quinchía', 'Mistrató', 'Pueblo Rico', 'Apia', 'Santuario', 'Balboa', 'La Celia',
    ],
  },
  { dep: 'San Andrés y Providencia', ciudades: ['San Andrés', 'Providencia', 'Santa Catalina'] },
  {
    dep: 'Santander',
    ciudades: [
      'Bucaramanga', 'Floridablanca', 'Girón', 'Piedecuesta', 'Barrancabermeja', 'San Gil', 'Socorro',
      'Málaga', 'Vélez', 'Barbosa', 'Lebrija', 'Rionegro', 'Betulia', 'El Playón',
      'Sabana de Torres', 'Puerto Wilches', 'Cimitarra', 'Landázuri', 'El Carmen de Chucurí',
      'San Vicente de Chucurí', 'Barichara', 'Villanueva', 'Curití', 'Charalá', 'Mogotes',
      'Galán', 'Contratación', 'Oiba', 'Suaita', 'Guadalupe', 'Aguada', 'Puente Nacional',
      'Guavatá', 'Bolívar', 'Jesús María', 'Palmar', 'Chima',
    ],
  },
  {
    dep: 'Sucre',
    ciudades: [
      'Sincelejo', 'Corozal', 'Sampués', 'San Marcos', 'Morroa', 'Sincé', 'El Roble', 'San Pedro',
      'Palmito', 'Santiago de Tolú', 'Coveñas', 'San Onofre', 'Toluviejo', 'Los Palmitos',
      'Galeras', 'La Unión', 'Buenavista', 'Majagual', 'Guaranda', 'Sucre', 'San Benito Abad',
      'Caimito', 'Ovejas',
    ],
  },
  {
    dep: 'Tolima',
    ciudades: [
      'Ibagué', 'Espinal', 'Melgar', 'Honda', 'Flandes', 'Líbano', 'Mariquita', 'Lérida',
      'Venadillo', 'Alvarado', 'Anzoátegui', 'Villahermosa', 'Fresno', 'Falan', 'Palocabildo',
      'Murillo', 'Santa Isabel', 'Casabianca', 'Herveo', 'Armero Guayabal', 'Prado',
      'Purificación', 'Saldaña', 'Guamo', 'Coyaima', 'Natagaima', 'Ortega', 'San Luis',
      'Valle de San Juan', 'Ataco', 'Chaparral', 'Roncesvalles', 'Rovira', 'Cajamarca',
      'Coello', 'Piedras', 'Ambalema', 'Cunday', 'Dolores', 'Icononzo', 'Villarrica',
    ],
  },
  {
    dep: 'Valle del Cauca',
    ciudades: [
      'Cali', 'Buenaventura', 'Palmira', 'Buga', 'Tulúa', 'Cartago', 'Jamundí', 'Yumbo',
      'Candelaria', 'El Cerrito', 'Ginebra', 'Guacarí', 'Dagua', 'La Cumbre', 'Vijes', 'Yotoco',
      'Restrepo', 'Calima', 'El Dovio', 'Versalles', 'La Unión', 'La Victoria', 'Roldanillo',
      'Bolívar', 'Toro', 'Ansermanuevo', 'El Águila', 'El Cairo', 'Alcalá', 'Ulloa',
      'Caicedonia', 'Sevilla', 'Bugalagrande', 'Trujillo', 'Riofrío', 'Andalucía', 'Zarzal',
      'Obando', 'Argelia', 'Florida', 'Pradera',
    ],
  },
  { dep: 'Vaupés', ciudades: ['Mitú', 'Carurú', 'Taraira', 'Papunahua', 'Yavaraté', 'Pacoa'] },
  { dep: 'Vichada', ciudades: ['Puerto Carreño', 'La Primavera', 'Santa Rosalía', 'Cumaribo'] },
];
