# PortPass — decree requirements matrix

Source reviewed: Décret n° 2026-753 du 8 août 2026, Article 1 creating Article R. 232-24 of the Code de la sécurité intérieure.

This document is a product-design mapping, not legal advice and not a claim that PortPass is compliant.

## 1. Vessel identification

| Decree field | PortPass field / behaviour | v0.2 status |
| --- | --- | --- |
| Vessel identification number | Numéro d’identification / immatriculation | Included |
| Name | Nom du navire | Included |
| Flag | Pavillon | Included |
| Port of registration | Port d’enregistrement | Included |
| MMSI / radio call sign / AIS identifier, where applicable | MMSI / indicatif / AIS | Included |
| Length | Longueur | Included |
| Make | Marque | Included |
| Model | Modèle | Included |
| Year launched | Année de mise à l’eau | Included |
| Year built | Année de construction | Included |

## 2. Owner — natural person

Required data: surname, usual name where applicable, first name, date of birth, place of birth, email, telephone, identity-document type and number where applicable, nationality.

PortPass v0.2 represents these in the demo owner record and makes explicit that identity-document data must be verified by the authorised port authority/delegate against an accepted document.

## 3. Owner — legal person

Required data: company name, nationality, SIRET or SIREN where applicable.

PortPass production model must support owner type = person / organisation. v0.2 exposes this requirement in the prototype but does not add a full company-owner workflow yet.

## 4. Persons aboard

For every person aboard: surname, usual name where applicable, first name, date of birth, place of birth, email, telephone, identity-document type and number where applicable, nationality.

PortPass v0.2 presents a complete fictional manifest and retains the harbour-side verification interaction.

## 5. Itinerary and mooring / berth

| Decree field | PortPass field / behaviour | v0.2 status |
| --- | --- | --- |
| Date of stopover | Arrival and departure dates | Included |
| Place of stationing | Emplacement / poste / mouillage | Included |
| Start time of stopover | Heure d’arrivée estimée + future actual arrival field | Included in demo |
| End time of stopover | Heure de départ estimée + future actual departure field | Included in demo |
| Departure port | Port de départ du voyage | Included |
| Previous stopover | Escale précédente | Included |
| Arrival port | Port d’arrivée | Included |
| Next planned stopover | Escale suivante prévue | Included |

Product note: the decree speaks of the actual start/end hours of the stopover. The skipper workflow can capture ETA/ETD, but production PortPass should allow the port to record or confirm actual start/end times.

## 6. Retention

Personal data in the treatment: retain for 2 years from collection.

Product requirement: automatic retention/deletion policy with no manual dependence on staff.

## 7. Access control

Access is limited to individually designated and specially authorised agents of the port authority, its delegate where applicable, or the port-police authority, for the needs of collection/transmission.

Product requirement: named accounts, role-based access and per-port authorisation. No shared generic harbour-master login in production.

## 8. Recipients / disclosure

Data may be supplied, under the conditions in the decree, to individually designated personnel of the national police, national gendarmerie, customs and Office national anti-fraude.

Product requirement: controlled disclosure/export workflow recording request, purpose, recipient and operator.

## 9. Audit logging

For automated processing, collection, modification, consultation, communication and deletion must be recorded. Consultation/communication logs must establish author identifier, date, time, reason and where applicable recipients. Those log details are retained for 3 years.

Product requirement: append-only audit trail covering all relevant operations, with 3-year retention for consultation/communication logs.

## 10. Data-subject information and rights

Article 14 GDPR information must be made available. Access, rectification and restriction rights are exercised with the processing authority subject to the statutory restrictions described in the decree. Right to object does not apply to this processing.

Product requirement: privacy-information view plus managed access/rectification/restriction request workflow.

## 11. Identity verification

When collecting owner/person-on-board identity information, the responsible port authority/delegate must verify identity data by presentation of one of the accepted documents referred to by the decree.

Product requirement: self-declaration prepares the record; it does not replace port-side identity verification. PortPass should record who performed the verification and when, without unnecessarily storing document images.

## 12. Commencement / ports in scope

Article 3 states that the decree's provisions enter into force at the same time as the ministerial order provided for by the second paragraph of Article L. 232-9.

Product requirement: do not market PortPass as legally compliant or mandatory for a named port until the applicable ministerial order and port scope have been confirmed.
